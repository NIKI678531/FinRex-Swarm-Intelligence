"""Swarm Tower factors from OASIS actions with FMP event fallback.

The 8 canonical Swarm factors are:

    sentiment_mean
    sentiment_velocity
    polarization
    consensus_speed
    bull_ratio
    topic_switch_rate
    kol_lead_signal
    event_intensity

OASIS remains the preferred source of crowd-intelligence actions. When OASIS
is missing or empty, FMP historical news/press-release/crypto-news events are
projected into the same 8-dimensional schema so the Swarm Tower has real
point-in-time inputs instead of a constant neutral 0.5 fallback.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .. import config

logger = logging.getLogger(__name__)

SWARM_FACTORS = [
    "sentiment_mean",
    "sentiment_velocity",
    "polarization",
    "consensus_speed",
    "bull_ratio",
    "topic_switch_rate",
    "kol_lead_signal",
    "event_intensity",
]

SOURCE_MODES = {"auto", "fmp_only", "oasis_only"}

_RISK_TERMS = {
    "risk", "regulator", "regulation", "sec", "lawsuit", "probe", "ban",
    "halt", "hack", "exploit", "liquidation", "default", "fraud",
    "bankrupt", "bankruptcy", "crash", "selloff", "warning", "downgrade",
}
_TRUSTED_SITES = {
    "reuters", "bloomberg", "business wire", "globenewswire", "pr newswire",
    "sec", "financial modeling prep", "financialmodelingprep",
}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']+|[\u4e00-\u9fff]+")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over",
    "after", "before", "says", "said", "will", "about", "market", "stock",
    "crypto", "price", "prices", "press", "release",
}


def _utc_timestamp(value):
    import pandas as pd

    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _empty_frame(quality: Optional[Dict[str, Any]] = None):
    import pandas as pd

    df = pd.DataFrame(columns=SWARM_FACTORS, index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    df.attrs["data_quality"] = quality or {}
    return df


def compute_swarm_factors(
    symbol: str,
    start,
    end,
    backfill_dir: Optional[Path] = None,
    *,
    source_mode: str = "auto",
    oasis_simulation_id: Optional[str] = None,
    sentiment_sources: Optional[List[str]] = None,
):
    """Aggregate OASIS/FMP inputs into a daily Swarm factor frame.

    `source_mode`:
      - auto: use OASIS rows where available and FMP rows for missing days.
      - fmp_only: use only FMP event-derived rows.
      - oasis_only: use only OASIS action-derived rows.
    """
    df, quality = compute_swarm_factor_bundle(
        symbol,
        start,
        end,
        backfill_dir=backfill_dir,
        source_mode=source_mode,
        oasis_simulation_id=oasis_simulation_id,
        sentiment_sources=sentiment_sources,
    )
    df.attrs["data_quality"] = quality
    return df


def compute_swarm_factor_bundle(
    symbol: str,
    start,
    end,
    backfill_dir: Optional[Path] = None,
    *,
    source_mode: str = "auto",
    oasis_simulation_id: Optional[str] = None,
    sentiment_sources: Optional[List[str]] = None,
) -> Tuple[Any, Dict[str, Any]]:
    import pandas as pd

    mode = (source_mode or "auto").lower()
    if mode not in SOURCE_MODES:
        mode = "auto"

    start_ts = _utc_timestamp(start)
    end_ts = _utc_timestamp(end)
    enabled_sources = {str(s).lower() for s in (sentiment_sources or ["fmp"])}

    oasis_rows: List[Dict[str, Any]] = []
    oasis_quality: Dict[str, Any] = {"available": False, "rows": 0}
    if mode != "fmp_only":
        oasis_rows, oasis_quality = _load_oasis_rows(
            symbol,
            start_ts,
            end_ts,
            backfill_dir=backfill_dir,
            oasis_simulation_id=oasis_simulation_id,
        )

    fmp_rows: List[Dict[str, Any]] = []
    fmp_quality: Dict[str, Any] = {"available": False, "rows": 0}
    if mode != "oasis_only" and "fmp" in enabled_sources:
        fmp_rows, fmp_quality = _load_fmp_rows(symbol, start_ts, end_ts)

    combined: Dict[pd.Timestamp, Dict[str, Any]] = {}
    selected_fmp = selected_oasis = 0
    if mode in {"auto", "fmp_only"}:
        for row in fmp_rows:
            ts = _utc_timestamp(row["ts"]).normalize()
            combined[ts] = {**row, "ts": ts, "_source": "fmp"}
            selected_fmp += 1
    if mode in {"auto", "oasis_only"}:
        for row in oasis_rows:
            ts = _utc_timestamp(row["ts"]).normalize()
            if mode == "auto" and ts in combined:
                selected_fmp -= 1
            combined[ts] = {**row, "ts": ts, "_source": "oasis"}
            selected_oasis += 1

    if not combined:
        quality = _build_quality(
            mode, start_ts, end_ts, oasis_rows, fmp_rows, 0, 0,
            oasis_quality, fmp_quality, effective_rows=0, frame_len=0,
        )
        return _empty_frame(quality), quality

    raw = pd.DataFrame(list(combined.values())).set_index("ts").sort_index()
    raw = raw[[c for c in raw.columns if c in SWARM_FACTORS]]
    frame = _normalize_daily_frame(raw)
    effective_rows = int((~frame.isna().all(axis=1)).sum()) if len(frame) else 0
    quality = _build_quality(
        mode, start_ts, end_ts, oasis_rows, fmp_rows, selected_oasis,
        selected_fmp, oasis_quality, fmp_quality, effective_rows, len(frame),
    )
    frame.attrs["data_quality"] = quality
    return frame, quality


def _build_quality(
    mode: str,
    start_ts,
    end_ts,
    oasis_rows: List[Dict[str, Any]],
    fmp_rows: List[Dict[str, Any]],
    selected_oasis: int,
    selected_fmp: int,
    oasis_quality: Dict[str, Any],
    fmp_quality: Dict[str, Any],
    effective_rows: int,
    frame_len: int,
) -> Dict[str, Any]:
    reasons = []
    if not oasis_rows:
        reasons.append("missing_or_empty_oasis_stream")
    if not fmp_rows:
        reasons.append("missing_or_empty_fmp_events")
    fallback_reason = None
    if not fmp_rows:
        fallback_reason = fmp_quality.get("fallback_reason") or "missing_or_empty_fmp_events"
    return {
        "source_mode": mode,
        "window": {"start": start_ts.isoformat(), "end": end_ts.isoformat()},
        "oasis_rows": int(len(oasis_rows)),
        "fmp_rows": int(len(fmp_rows)),
        "selected_oasis_rows": int(selected_oasis),
        "selected_fmp_rows": int(max(0, selected_fmp)),
        "effective_rows": int(effective_rows),
        "coverage_ratio": (effective_rows / frame_len) if frame_len else 0.0,
        "constant_signal_warning": False,
        "reasons": reasons,
        "news_endpoint_family": fmp_quality.get("endpoint_family") or [],
        "news_symbol_variants": fmp_quality.get("symbol_variants") or [],
        "news_cache_hit": bool(fmp_quality.get("cache_hit")),
        "article_count": int(fmp_quality.get("article_count") or len(fmp_rows)),
        "fallback_reason": fallback_reason,
        "oasis": oasis_quality,
        "fmp": fmp_quality,
    }


def _normalize_daily_frame(raw):
    import numpy as np
    import pandas as pd

    if raw.empty:
        return _empty_frame()
    raw = raw.copy()
    raw.index = pd.DatetimeIndex([_utc_timestamp(ts).normalize() for ts in raw.index])
    raw = raw.groupby(raw.index).mean(numeric_only=True).sort_index()
    full_idx = pd.date_range(raw.index.min(), raw.index.max(), freq="D", tz="UTC")
    df = raw.reindex(full_idx).ffill(limit=config.SWARM_FFILL_LIMIT)

    if "sentiment_mean" in df:
        df["sentiment_velocity"] = df["sentiment_mean"].diff(5)
    if "polarization" in df:
        df["consensus_speed"] = -df["polarization"].diff(1)

    win = config.SWARM_ZSCORE_WINDOW
    for col in SWARM_FACTORS:
        if col not in df.columns:
            df[col] = np.nan
            continue
        s = df[col].astype(float)
        non_null = int(s.notna().sum())
        min_periods = min(max(5, win // 4), max(2, non_null))
        mean = s.rolling(win, min_periods=min_periods).mean()
        std = s.rolling(win, min_periods=min_periods).std().replace(0, np.nan)
        df[col] = ((s - mean) / std).clip(-5, 5)
    df.index.name = "ts"
    return df[SWARM_FACTORS]


def _load_oasis_rows(
    symbol: str,
    start_ts,
    end_ts,
    *,
    backfill_dir: Optional[Path],
    oasis_simulation_id: Optional[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if oasis_simulation_id:
        return _load_oasis_simulation_id(oasis_simulation_id, start_ts, end_ts)

    rows: List[Dict[str, Any]] = []
    quality = {
        "available": False,
        "rows": 0,
        "simulation_id": None,
        "reason": "missing_or_empty_oasis_stream",
    }
    dates = _list_simulation_dates(symbol, backfill_dir)
    for sim_date, sim_path in dates:
        sim_ts = _utc_timestamp(sim_date).normalize()
        if sim_ts < start_ts - _pd_timedelta(days=7):
            continue
        if sim_ts > end_ts + _pd_timedelta(days=1):
            continue
        row = _extract_one(sim_path, sim_ts)
        if row is None:
            continue
        row["ts"] = sim_ts
        rows.append(row)
    if rows:
        quality.update(available=True, rows=len(rows), reason=None)
    return rows, quality


def _pd_timedelta(**kwargs):
    import pandas as pd

    return pd.Timedelta(**kwargs)


def _load_oasis_simulation_id(simulation_id: str, start_ts, end_ts) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        from app.services.historical_signals.oasis_factor_builder import build_oasis_daily_factors

        payload = build_oasis_daily_factors(
            simulation_id,
            start_ts.to_pydatetime(),
            end_ts.to_pydatetime(),
        )
    except Exception as exc:  # noqa: BLE001
        return [], {"available": False, "simulation_id": simulation_id, "error": str(exc)}

    for day, row in (payload.get("rows_by_date") or {}).items():
        ts = _utc_timestamp(day).normalize()
        if ts < start_ts or ts > end_ts:
            continue
        projected = _project_to_swarm_factors(row)
        if projected:
            projected["ts"] = ts
            rows.append(projected)
    coverage = payload.get("coverage") or {}
    return rows, {
        **coverage,
        "available": bool(rows),
        "rows": len(rows),
        "simulation_id": simulation_id,
    }


def _list_simulation_dates(symbol: str, backfill_dir: Optional[Path]):
    import pandas as pd

    candidates = []
    roots = []
    if backfill_dir is not None:
        roots.append(Path(backfill_dir))
    roots.append(config.OASIS_BACKFILL_DIR / symbol)
    legacy = Path(__file__).resolve().parents[3] / "uploads" / "simulations"
    if legacy.exists():
        roots.append(legacy)

    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            ts = _parse_date_from_name(p.name)
            if ts is None:
                ts = pd.to_datetime(p.stat().st_mtime, unit="s", utc=True)
            candidates.append((ts, p))
    return sorted(candidates, key=lambda x: x[0])


def _parse_date_from_name(name: str):
    m = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", name)
    if not m:
        return None
    try:
        return _utc_timestamp(f"{m[1]}-{m[2]}-{m[3]}")
    except Exception:
        return None


def _extract_one(sim_path: Path, sim_ts=None) -> Optional[dict]:
    if sim_path.name.startswith("sim_"):
        start = sim_ts or _utc_timestamp(sim_path.stat().st_mtime)
        end = start + _pd_timedelta(days=1)
        rows, _quality = _load_oasis_simulation_id(sim_path.name, start, end)
        if rows:
            out = dict(rows[0])
            out.pop("ts", None)
            return out

    actions = _load_action_dicts(sim_path)
    if not actions:
        return None
    return _row_from_action_dicts(actions)


def _project_to_swarm_factors(row: dict) -> dict:
    mapping = {
        "sentiment_mean": ["sentiment_mean", "sentiment", "oasis_sentiment"],
        "sentiment_velocity": ["sentiment_velocity", "velocity_z", "oasis_velocity_z"],
        "polarization": ["polarization", "disagreement", "oasis_disagreement"],
        "consensus_speed": ["consensus_speed", "consensus", "oasis_consensus"],
        "bull_ratio": ["bull_ratio", "oasis_fomo_score"],
        "topic_switch_rate": ["topic_switch_rate", "oasis_cross_platform_spread"],
        "kol_lead_signal": ["kol_lead_signal", "oasis_fomo_score"],
        "event_intensity": ["event_intensity", "oasis_pulse_score", "oasis_risk_intensity"],
    }
    out = {}
    for target, candidates in mapping.items():
        for key in candidates:
            value = row.get(key)
            if value is None:
                continue
            try:
                out[target] = float(value)
                break
            except (TypeError, ValueError):
                continue
    return out


def _load_action_dicts(sim_path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    paths = [
        sim_path / "twitter" / "actions.jsonl",
        sim_path / "reddit" / "actions.jsonl",
        sim_path / "actions.jsonl",
    ]
    for path in paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if item.get("event_type") and not item.get("action_type"):
                continue
            if item.get("action_type") or _extract_text(item):
                out.append(item)
    return out


def _row_from_action_dicts(actions: List[Dict[str, Any]]) -> Dict[str, float]:
    try:
        from app.services.historical_signals.sentiment_replayer import score_text
    except Exception:  # noqa: BLE001
        score_text = _fallback_score_text

    scores = []
    for action in actions:
        scores.append(float(score_text(_extract_text(action))))
    n = max(1, len(scores))
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    bull = sum(1 for s in scores if s > 0.1)
    return {
        "sentiment_mean": mean,
        "polarization": math.sqrt(max(0.0, variance)),
        "bull_ratio": bull / n,
        "kol_lead_signal": mean,
        "event_intensity": math.log1p(n),
    }


def _load_fmp_rows(symbol: str, start_ts, end_ts) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    try:
        from app.services.historical_signals import data_loader_fmp

        payload = data_loader_fmp.fetch_window_with_coverage(
            symbol,
            start_ts.to_pydatetime(),
            end_ts.to_pydatetime(),
        )
        articles = payload.get("items") or []
        coverage = payload.get("coverage") or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP event load failed for %s: %s", symbol, exc)
        return [], {"available": False, "rows": 0, "error": str(exc)}

    rows = _fmp_articles_to_rows(articles)
    coverage = {**coverage, "available": bool(rows), "rows": len(rows)}
    return rows, coverage


def _fmp_articles_to_rows(articles: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        from app.services.historical_signals.sentiment_replayer import score_article
    except Exception:  # noqa: BLE001
        score_article = lambda article: _fallback_score_text(  # noqa: E731
            " ".join(filter(None, [article.get("title", ""), article.get("text", "")]))
        )

    buckets: Dict[str, Dict[str, Any]] = {}
    for article in articles:
        ts = _parse_article_ts(article)
        if ts is None:
            continue
        day = ts.strftime("%Y-%m-%d")
        score = float(score_article(article))
        weight = _article_weight(article)
        text = " ".join(filter(None, [str(article.get("title") or ""), str(article.get("text") or "")]))
        bucket = buckets.setdefault(day, {
            "scores": [],
            "weights": [],
            "high_weight_scores": [],
            "tokens": set(),
            "risk_hits": 0,
            "press_count": 0,
        })
        bucket["scores"].append(score)
        bucket["weights"].append(weight)
        if weight > 1.25:
            bucket["high_weight_scores"].append((score, weight))
        bucket["tokens"].update(_topic_tokens(text))
        bucket["risk_hits"] += _contains_terms(text, _RISK_TERMS)
        if str(article.get("source_type") or "").lower() == "press_release":
            bucket["press_count"] += 1

    rows: List[Dict[str, Any]] = []
    previous_tokens: Optional[set] = None
    for day in sorted(buckets):
        bucket = buckets[day]
        scores = bucket["scores"]
        weights = bucket["weights"]
        total_w = sum(weights) or 1.0
        mean = sum(s * w for s, w in zip(scores, weights)) / total_w
        variance = sum(w * (s - mean) ** 2 for s, w in zip(scores, weights)) / total_w
        high = bucket["high_weight_scores"]
        high_total = sum(w for _s, w in high)
        kol = (sum(s * w for s, w in high) / high_total) if high_total else mean
        tokens = bucket["tokens"]
        if previous_tokens is None:
            switch = 0.0
        else:
            union = len(tokens | previous_tokens)
            switch = 0.0 if union == 0 else 1.0 - (len(tokens & previous_tokens) / union)
        previous_tokens = set(tokens)
        n = len(scores)
        bull = sum(1 for s in scores if s > 0.1)
        event_intensity = (
            math.log1p(n)
            + 0.25 * min(6, bucket["risk_hits"])
            + 0.35 * bucket["press_count"]
        )
        rows.append({
            "ts": _utc_timestamp(day),
            "sentiment_mean": mean,
            "polarization": math.sqrt(max(0.0, variance)),
            "bull_ratio": bull / max(1, n),
            "topic_switch_rate": switch,
            "kol_lead_signal": kol,
            "event_intensity": event_intensity,
        })
    return rows


def _parse_article_ts(article: Dict[str, Any]):
    raw = article.get("published_at") or article.get("publishedDate") or article.get("date")
    if not raw:
        return None
    try:
        return _utc_timestamp(raw)
    except Exception:
        return None


def _article_weight(article: Dict[str, Any]) -> float:
    weight = 1.0
    source_type = str(article.get("source_type") or "").lower()
    site = str(article.get("site") or "").lower()
    if source_type == "press_release":
        weight += 0.5
    if any(token in site for token in _TRUSTED_SITES):
        weight += 0.4
    return weight


def _topic_tokens(text: str) -> set:
    tokens = set()
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) <= 2 or token in _STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def _contains_terms(text: str, terms: Iterable[str]) -> int:
    low = text.lower()
    return sum(1 for term in terms if term in low)


def _extract_text(item: Dict[str, Any]) -> str:
    chunks: List[str] = []
    action_args = item.get("action_args") if isinstance(item.get("action_args"), dict) else {}
    for source in (item, action_args):
        for key in ("content", "text", "body", "query", "post_content", "comment_content", "result"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value.strip())
    return "\n".join(chunks)


def _fallback_score_text(text: str) -> float:
    if not text:
        return 0.0
    low = text.lower()
    pos = _contains_terms(low, {"bull", "buy", "rally", "surge", "beat", "upgrade", "growth"})
    neg = _contains_terms(low, {"bear", "sell", "crash", "drop", "miss", "downgrade", "risk"})
    total = pos + neg
    return 0.0 if total == 0 else (pos - neg) / total
