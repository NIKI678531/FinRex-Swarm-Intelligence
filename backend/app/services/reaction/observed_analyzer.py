"""Rule-based observed comment analysis.

This intentionally has no hard dependency on an LLM. It provides stable,
inspectable output for the UI and can later be swapped for a model-backed
classifier behind the same contract.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

from .schema import ObservedAnalysis, ReactionComment, ReactionEvent


POSITIVE_TERMS = {
    "bull", "bullish", "buy", "bought", "moon", "pump", "breakout", "rally",
    "strong", "beat", "growth", "upside", "long", "support", "good", "great",
    "positive", "recover", "rebound", "看多", "利好", "上涨", "买入", "支持", "反弹",
}
NEGATIVE_TERMS = {
    "bear", "bearish", "sell", "sold", "dump", "crash", "scam", "fraud", "risk",
    "weak", "miss", "downside", "short", "bad", "negative", "drop", "fear", "panic",
    "看空", "利空", "下跌", "卖出", "反对", "崩", "风险", "恐慌", "骗局",
}
ANGER_TERMS = {"angry", "rage", "outrage", "hate", "boycott", "愤怒", "抵制", "离谱"}
UNCERTAINTY_TERMS = {"maybe", "unclear", "wait", "watch", "rumor", "source", "verify", "观望", "不确定", "传闻", "求证"}
RISK_TERMS = {"lawsuit", "regulator", "sec", "hack", "halt", "delist", "liquidation", "监管", "诉讼", "爆仓", "黑客", "退市"}

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "you", "they",
    "have", "has", "not", "but", "just", "about", "into", "out", "will", "would", "can",
    "should", "could", "its", "it's", "i", "to", "of", "in", "on", "is", "a", "an", "it",
}


def _tokens(text: str) -> List[str]:
    lower = text.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_+.-]{1,}|[\u4e00-\u9fff]{2,}", lower)
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def _score_comment(text: str) -> Tuple[str, str, float]:
    tokens = set(_tokens(text))
    lower = text.lower()
    pos = sum(1 for t in POSITIVE_TERMS if t.lower() in lower or t in tokens)
    neg = sum(1 for t in NEGATIVE_TERMS if t.lower() in lower or t in tokens)
    uncertainty = sum(1 for t in UNCERTAINTY_TERMS if t.lower() in lower or t in tokens)
    anger = sum(1 for t in ANGER_TERMS if t.lower() in lower or t in tokens)

    score = pos - neg - (0.4 * anger)
    if uncertainty and abs(score) < 1.5:
        sentiment = "neutral"
        stance = "skeptical"
    elif score > 0:
        sentiment = "positive"
        stance = "supportive"
    elif score < 0:
        sentiment = "negative"
        stance = "opposing" if neg >= pos + 1 else "skeptical"
    else:
        sentiment = "neutral"
        stance = "neutral"
    return sentiment, stance, score


def _ratio(counter: Counter, total: int) -> Dict[str, float]:
    if total <= 0:
        return {}
    keys = sorted(counter.keys())
    return {key: round(counter[key] / total, 4) for key in keys}


def _topic_counts(comments: List[ReactionComment], event: ReactionEvent) -> List[Dict[str, object]]:
    counts = Counter()
    examples: Dict[str, str] = {}
    event_terms = set(_tokens(event.to_text(max_chars=1200)))
    for comment in comments:
        token_counts = Counter(_tokens(comment.text))
        for token, count in token_counts.items():
            if len(token) <= 2 and token not in event_terms:
                continue
            counts[token] += count
            examples.setdefault(token, comment.text[:180])
    return [
        {"topic": topic, "count": count, "example": examples.get(topic, "")}
        for topic, count in counts.most_common(10)
    ]


def _representative_comments(scored: List[Tuple[ReactionComment, str, str, float]]) -> List[Dict[str, object]]:
    by_sentiment: Dict[str, List[Tuple[ReactionComment, str, str, float]]] = defaultdict(list)
    for item in scored:
        by_sentiment[item[1]].append(item)

    reps: List[Dict[str, object]] = []
    for sentiment in ("positive", "negative", "neutral"):
        candidates = sorted(
            by_sentiment.get(sentiment, []),
            key=lambda x: (abs(x[3]), x[0].like_count, len(x[0].text)),
            reverse=True,
        )
        for comment, _, stance, score in candidates[:2]:
            reps.append({
                "text": comment.text[:300],
                "sentiment": sentiment,
                "stance": stance,
                "score": round(score, 2),
                "author": comment.author,
                "like_count": comment.like_count,
            })
    return reps[:6]


def analyze_observed(event: ReactionEvent, comments: List[ReactionComment]) -> ObservedAnalysis:
    total = len(comments)
    if total == 0:
        return ObservedAnalysis(
            comment_count=0,
            unique_authors=0,
            sentiment_distribution={},
            stance_distribution={},
            data_quality="none",
            summary="No real comment text was provided; only agent simulation can be used.",
        )

    scored = [(comment, *_score_comment(comment.text)) for comment in comments]
    sentiment_counts = Counter(item[1] for item in scored)
    stance_counts = Counter(item[2] for item in scored)
    authors = {c.author for c in comments if c.author}
    top_topics = _topic_counts(comments, event)
    risk_signals: List[str] = []
    if any(_contains_any(c.text, RISK_TERMS) for c in comments):
        risk_signals.append("Regulatory, security, legal, or liquidation language appears in comments.")
    if sentiment_counts.get("negative", 0) / max(total, 1) >= 0.45:
        risk_signals.append("Negative voices are a large share of the observed comment sample.")
    if sentiment_counts.get("positive", 0) / max(total, 1) >= 0.60:
        risk_signals.append("Positive voices dominate; check whether hype or one-sided promotion is inflating the sample.")

    data_quality = "high" if total >= 100 else "medium" if total >= 25 else "low"
    positive = sentiment_counts.get("positive", 0)
    negative = sentiment_counts.get("negative", 0)
    neutral = sentiment_counts.get("neutral", 0)
    summary = (
        f"Observed {total} comments: {positive} positive, {negative} negative, "
        f"{neutral} neutral. Top topics: "
        + ", ".join(t["topic"] for t in top_topics[:5])
    )

    return ObservedAnalysis(
        comment_count=total,
        unique_authors=len(authors) if authors else 0,
        sentiment_distribution=_ratio(sentiment_counts, total),
        stance_distribution=_ratio(stance_counts, total),
        top_topics=top_topics,
        representative_comments=_representative_comments(scored),
        risk_signals=risk_signals,
        data_quality=data_quality,
        summary=summary,
    )
