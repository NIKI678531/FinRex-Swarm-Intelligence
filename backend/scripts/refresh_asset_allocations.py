"""Scheduled refresh of asset-allocation bundles.

Iterates all reports that already have a cached asset-allocation bundle and
regenerates them with fresh market data. Intended to be wired up to a cron
job / Windows Task Scheduler — e.g. once per trading day after HK close
(~17:00 HKT).

Usage:
    python -m scripts.refresh_asset_allocations            # all cached
    python -m scripts.refresh_asset_allocations --max 20   # limit batch
    python -m scripts.refresh_asset_allocations --report-id <id>

The script never raises on individual failures so one bad report cannot
break the batch.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Iterable, List, Optional

# Make ``app`` importable when run as a script from the backend folder.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import Config  # noqa: E402
from app.services.asset_forecast import AssetForecastService  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("refresh_alloc")

STORAGE_DIR = os.path.join(Config.UPLOAD_FOLDER, "asset_allocation")


def _get_report_manager():
    """Lazy import — ReportManager pulls in optional Zep deps that may be
    absent in lightweight cron environments."""
    from app.services.report_agent import ReportManager  # noqa: WPS433
    return ReportManager


def _list_cached_report_ids() -> List[str]:
    if not os.path.isdir(STORAGE_DIR):
        return []
    out: List[str] = []
    for name in sorted(os.listdir(STORAGE_DIR)):
        if name.endswith(".json"):
            out.append(name[:-5])
    return out


def _refresh_one(report_id: str, horizon_days: int = 5) -> bool:
    try:
        ReportManager = _get_report_manager()
        report = ReportManager.get_report(report_id)
        if not report:
            log.warning("report %s not found, skipping", report_id)
            return False
        bundle = AssetForecastService.build_for_report(
            report.to_dict(),
            force=True,
            horizon_days=horizon_days,
        )
        log.info("refreshed %s — %d picks, generated_at=%s",
                 report_id,
                 len(bundle.get("top_picks") or []),
                 bundle.get("generated_at"))
        return True
    except Exception as exc:
        log.error("refresh failed for %s: %s", report_id, exc)
        return False


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report-id", help="refresh a single report id")
    p.add_argument("--max", type=int, default=0, help="cap how many reports to refresh")
    p.add_argument("--horizon-days", type=int, default=5,
                   help="forecast horizon in trading days (5/10/21)")
    p.add_argument("--sleep", type=float, default=1.0,
                   help="sleep between reports to be kind to yfinance")
    args = p.parse_args(argv)

    targets: Iterable[str]
    if args.report_id:
        targets = [args.report_id]
    else:
        targets = _list_cached_report_ids()
        if args.max > 0:
            targets = list(targets)[: args.max]

    targets = list(targets)
    log.info("refreshing %d report(s) (horizon=%dd)", len(targets), args.horizon_days)

    ok = fail = 0
    for rid in targets:
        if _refresh_one(rid, horizon_days=args.horizon_days):
            ok += 1
        else:
            fail += 1
        if args.sleep > 0:
            time.sleep(args.sleep)

    log.info("done: ok=%d, fail=%d", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
