"""APScheduler driver for the system-A auto paper-trader.

Periodically fuses multi-source signals across the configured watchlist and
places market orders on a dedicated, isolated paper account. Parked limit
orders are matched on a faster cadence so fills are reflected before the next
sizing decision.

Schedule (UTC):
  * :05 of 13/19/03 — auto-trade cycle (fuse signals → place orders)
  * every 15 min    — match parked limit orders + mark-to-market refresh

Run as: ``python -m backend.scripts.paper_trading_scheduler``
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure backend/ is on sys.path when run as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
from apscheduler.triggers.cron import CronTrigger  # type: ignore

from app.quant.paper_trading import auto_trader, portfolio

logger = logging.getLogger("finrex.paper_trading.scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def job_auto_trade(label: str = "primary") -> None:
    logger.info("[auto:%s] running signal-driven cycle", label)
    try:
        account_id = auto_trader.get_or_create_auto_account()
        result = auto_trader.run_cycle(account_id)
        logger.info(
            "[auto:%s] account=%s pending_filled=%d executed=%d/%d",
            label, account_id, result.get("pending_filled", 0),
            result.get("executed", 0), len(result.get("decisions", [])),
        )
        for d in result.get("decisions", []):
            if d["status"] != "skipped":
                logger.info(
                    "[auto:%s]   %s %s — %s", label,
                    d["symbol"], d["status"], d.get("reason"),
                )
    except Exception:  # noqa: BLE001
        logger.exception("[auto:%s] failed", label)


def job_match_pending() -> None:
    logger.info("[match] revisiting parked limit orders")
    try:
        account_id = auto_trader.get_or_create_auto_account()
        filled = portfolio.match_pending_orders(account_id)
        logger.info("[match] filled %d parked orders", len(filled))
    except Exception:  # noqa: BLE001
        logger.exception("[match] failed")


def main() -> None:
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(lambda: job_auto_trade("primary"), CronTrigger(hour=13, minute=5), id="auto_primary", replace_existing=True)
    sched.add_job(lambda: job_auto_trade("evening"), CronTrigger(hour=19, minute=5), id="auto_evening", replace_existing=True)
    sched.add_job(lambda: job_auto_trade("overnight"), CronTrigger(hour=3, minute=5), id="auto_overnight", replace_existing=True)
    sched.add_job(job_match_pending, CronTrigger(minute="*/15"), id="match_pending", replace_existing=True)
    logger.info("paper-trading auto scheduler ready (UTC)")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler shutting down")


if __name__ == "__main__":
    main()
