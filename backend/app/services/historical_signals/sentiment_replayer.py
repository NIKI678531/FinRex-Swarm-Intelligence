"""Sentiment scoring for backtest articles.

Lightweight, dependency-free pipeline:
- Lexicon-based finance sentiment (Loughran-McDonald style mini lexicon)
- Volume / engagement counters

This is intentionally simple so the engine can run offline without
LLM/HF inference. The architecture allows swapping in a finBERT pipeline
later by replacing `score_article`.

Output per (day, source) bucket:
    {
        "date": "YYYY-MM-DD",
        "source": "fmp"|"binance_d1",
        "n_articles": int,
        "n_engagement": int,        # likes+comments where available
        "sentiment_finbert": float, # in [-1, 1]
        "sentiment_emotion": float, # in [-1, 1]; here = derivative of sentiment
    }
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

logger = logging.getLogger("finrex.backtest.sentiment")


# Mini lexicon — keep small but directional. Negation handled via word window.
_POS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "bullish", "soar",
    "soars", "outperform", "growth", "profit", "gain", "gains", "upgrade",
    "record", "strong", "boom", "boost", "boosts", "advance", "breakout",
    "approve", "approved", "win", "wins", "expand", "raise", "raises",
}
_NEG = {
    "miss", "misses", "drop", "drops", "plunge", "plunges", "bearish", "fall",
    "falls", "downgrade", "loss", "losses", "decline", "weak", "crash",
    "concern", "concerns", "warn", "warns", "slump", "lawsuit", "probe",
    "investigation", "ban", "banned", "halt", "delay", "fine", "fraud",
    "default", "bankruptcy", "hack", "hacked", "exploit", "selloff",
}
_NEGATORS = {"not", "no", "never", "n't", "without", "fails", "failed"}

_TOKEN_RE = re.compile(r"[A-Za-z']+")


def score_text(text: str) -> float:
    """Return sentiment in [-1, 1]; 0 if no signal."""
    if not text:
        return 0.0
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    if not tokens:
        return 0.0
    pos = neg = 0
    for i, tok in enumerate(tokens):
        is_pos = tok in _POS
        is_neg = tok in _NEG
        if not (is_pos or is_neg):
            continue
        # Look back 2 words for a negator.
        flipped = any(t in _NEGATORS for t in tokens[max(0, i - 2):i])
        if is_pos:
            neg += 1 if flipped else 0
            pos += 0 if flipped else 1
        else:
            pos += 1 if flipped else 0
            neg += 0 if flipped else 1
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def score_article(article: Dict[str, Any]) -> float:
    blob = " ".join(filter(None, [article.get("title", ""), article.get("text", "")]))
    return score_text(blob)


def _parse_day(item: Dict[str, Any]) -> str | None:
    raw = item.get("published_at")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.strftime("%Y-%m-%d")


def aggregate_daily(
    articles: Iterable[Dict[str, Any]],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Bucket articles by (day, source) and produce daily features."""
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(lambda: {
        "n_articles": 0,
        "n_engagement": 0,
        "score_sum": 0.0,
        "abs_score_sum": 0.0,
    })
    for art in articles:
        day = _parse_day(art)
        if day is None:
            continue
        key = (day, art.get("source", "unknown"))
        s = score_article(art)
        b = buckets[key]
        b["n_articles"] += 1
        b["n_engagement"] += int(art.get("comment_count", 0) or 0) + int(art.get("like_count", 0) or 0)
        b["score_sum"] += s
        b["abs_score_sum"] += abs(s)

    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (day, source), b in buckets.items():
        n = max(b["n_articles"], 1)
        out[(day, source)] = {
            "date": day,
            "source": source,
            "n_articles": b["n_articles"],
            "n_engagement": b["n_engagement"],
            "sentiment_finbert": round(b["score_sum"] / n, 4),
            "sentiment_emotion": round(b["abs_score_sum"] / n, 4),
        }
    return out


def merge_daily(
    fmp_articles: Iterable[Dict[str, Any]],
    binance_articles: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Combine sources into one row per day with weighted aggregation.

    Engagement (Binance) acts as a soft weight on the sentiment score.
    """
    fmp_buckets = aggregate_daily(fmp_articles)
    bin_buckets = aggregate_daily(binance_articles)

    days = sorted({k[0] for k in fmp_buckets} | {k[0] for k in bin_buckets})
    rows: List[Dict[str, Any]] = []
    for day in days:
        fmp = fmp_buckets.get((day, "fmp"))
        bina = bin_buckets.get((day, "binance_d1"))
        n_fmp = fmp["n_articles"] if fmp else 0
        n_bin = bina["n_articles"] if bina else 0
        eng_bin = bina["n_engagement"] if bina else 0
        # weights: each FMP article = 1, each Binance article = 1 + log1p(engagement / max(1, n_bin))
        w_fmp = float(n_fmp)
        # avoid divide-by-zero
        bin_engagement_per_article = (eng_bin / n_bin) if n_bin else 0.0
        w_bin = float(n_bin) * (1.0 + min(2.0, bin_engagement_per_article / 50.0))
        total_w = w_fmp + w_bin
        if total_w == 0:
            continue
        sent = (
            (fmp["sentiment_finbert"] if fmp else 0.0) * w_fmp
            + (bina["sentiment_finbert"] if bina else 0.0) * w_bin
        ) / total_w
        emo = (
            (fmp["sentiment_emotion"] if fmp else 0.0) * w_fmp
            + (bina["sentiment_emotion"] if bina else 0.0) * w_bin
        ) / total_w
        rows.append({
            "date": day,
            "n_articles_fmp": n_fmp,
            "n_articles_binance": n_bin,
            "engagement_binance": eng_bin,
            "sentiment_finbert": round(sent, 4),
            "sentiment_emotion": round(emo, 4),
            "news_volume": n_fmp,
            "social_volume": n_bin,
        })
    return rows
