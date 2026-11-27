"""APScheduler for the weekly bins-based Validation Lab.

Schedule (UTC):
  * Mon 00:05  — create new weekly cycle, run snapshot, place bets
  * Daily 12:00 — refresh forecast (no new bets; informational)
  * Sun 23:59  — settle the cycle once close price is available
  * Mon 00:01  — sweep any unsettled cycles (catch-up safety net)

Run as: ``python -m backend.scripts.weekly_validation_scheduler``
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
from apscheduler.triggers.cron import CronTrigger  # type: ignore

from app.services.validation import weekly_engine

logger = logging.getLogger("finrex.weekly_validation.scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SYMBOLS = ("BTC",)


def job_open_cycle():
    for sym in SYMBOLS:
        try:
            data = weekly_engine.run_snapshot(sym, place_bets=True)
            logger.info("[open] cycle=%s positions=%d", data.get("cycle_id"), len(data.get("positions") or []))
        except Exception:  # noqa: BLE001
            logger.exception("[open] failed for %s", sym)


def job_refresh_forecast():
    for sym in SYMBOLS:
        try:
            weekly_engine.run_snapshot(sym, place_bets=False)
            logger.info("[refresh] forecast updated for %s", sym)
        except Exception:  # noqa: BLE001
            logger.exception("[refresh] failed for %s", sym)


def job_settle():
    for sym in SYMBOLS:
        try:
            settled = weekly_engine.settle_due_cycles(sym)
            logger.info("[settle] %s settled=%d", sym, len(settled))
        except Exception:  # noqa: BLE001
            logger.exception("[settle] failed for %s", sym)


def main():
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(job_open_cycle, CronTrigger(day_of_week="mon", hour=0, minute=5), id="open_cycle")
    scheduler.add_job(job_refresh_forecast, CronTrigger(hour=12, minute=0), id="refresh_forecast")
    scheduler.add_job(job_settle, CronTrigger(day_of_week="sun", hour=23, minute=59), id="settle")
    scheduler.add_job(job_settle, CronTrigger(day_of_week="mon", hour=0, minute=1), id="settle_sweep")
    logger.info("weekly validation scheduler starting (UTC)")
    scheduler.start()


if __name__ == "__main__":
    main()
