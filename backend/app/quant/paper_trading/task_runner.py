"""In-memory background task runner for long auto-trading cycles.

The auto-trader runs an LLM forecast + market fetch for every watchlist symbol,
which easily exceeds the frontend's HTTP timeout. Instead of blocking the
request, callers ``start()`` a task (returns a ``task_id`` immediately) and poll
``get()`` for incremental progress.

Tasks live in a process-local dict — fine for the single-process Flask dev/app
server used here. Completed tasks are pruned after ``_TTL_SECONDS``.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 3600  # keep finished tasks around for an hour for late pollers


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _prune_locked() -> None:
    cutoff = time.time() - _TTL_SECONDS
    stale = [tid for tid, t in _TASKS.items()
             if t.get("status") in {"done", "error"} and t.get("_finished_at", 0) < cutoff]
    for tid in stale:
        _TASKS.pop(tid, None)


def start_auto_trade(account_id: str, watchlist: Optional[List[str]]) -> str:
    """Kick off an auto-trade cycle in a daemon thread; return its task id."""
    from . import auto_trader
    from .. import config

    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    total = len(watchlist) if watchlist is not None else len(config.AUTO_TRADE_WATCHLIST)

    with _LOCK:
        _prune_locked()
        _TASKS[task_id] = {
            "task_id": task_id,
            "account_id": account_id,
            "status": "running",
            "done": 0,
            "total": total,
            "current_symbol": None,
            "decisions": [],
            "result": None,
            "error": None,
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
        }

    def _progress(done: int, total_: int, symbol: str, decision: Dict[str, Any]) -> None:
        with _LOCK:
            task = _TASKS.get(task_id)
            if not task:
                return
            task["done"] = done
            task["total"] = total_
            task["current_symbol"] = symbol
            task["decisions"].append(decision)
            task["updated_at"] = _now_iso()

    def _run() -> None:
        try:
            result = auto_trader.run_cycle(account_id, watchlist=watchlist, progress_cb=_progress)
            with _LOCK:
                task = _TASKS.get(task_id)
                if task is not None:
                    task["status"] = "error" if result.get("error") else "done"
                    task["result"] = result
                    task["error"] = result.get("error")
                    task["current_symbol"] = None
                    task["updated_at"] = _now_iso()
                    task["_finished_at"] = time.time()
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                task = _TASKS.get(task_id)
                if task is not None:
                    task["status"] = "error"
                    task["error"] = str(exc)
                    task["updated_at"] = _now_iso()
                    task["_finished_at"] = time.time()

    threading.Thread(target=_run, name=f"auto-trade-{task_id}", daemon=True).start()
    return task_id


def get(task_id: str) -> Optional[Dict[str, Any]]:
    """Return a public snapshot of a task, or ``None`` if unknown."""
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return None
        return {k: v for k, v in task.items() if not k.startswith("_")}
