"""Estimate how incomplete an observed comment sample may be."""

from __future__ import annotations

from typing import List

from .schema import ObservedAnalysis, ReactionComment, ReactionEvent, SampleBiasAnalysis


def analyze_sample_bias(
    event: ReactionEvent,
    comments: List[ReactionComment],
    observed: ObservedAnalysis,
) -> SampleBiasAnalysis:
    count = len(comments)
    if count == 0:
        return SampleBiasAnalysis(
            bias_level="complete_gap",
            coverage_level="none",
            risks=["No real comment text is available."],
            likely_underrepresented_groups=[
                "silent readers",
                "late-arriving users",
                "risk-averse users",
                "users outside the captured platform",
            ],
            rationale="The run depends on agent simulation because observed reactions are absent.",
        )

    authors = [c.author for c in comments if c.author]
    unique_authors = len(set(authors))
    no_author_ratio = 1 - (len(authors) / count)
    sentiment = observed.sentiment_distribution or {}
    max_sentiment_share = max(sentiment.values()) if sentiment else 0
    engagement_values = sorted([c.like_count for c in comments if c.like_count > 0], reverse=True)
    top_like_share = 0.0
    if engagement_values:
        top_like_share = sum(engagement_values[: max(1, len(engagement_values) // 10)]) / max(sum(engagement_values), 1)

    risks: List[str] = []
    if count < 25:
        risks.append("Small observed sample; a few active voices can dominate the conclusion.")
    if unique_authors and unique_authors < max(5, count * 0.35):
        risks.append("Repeated or concentrated authorship may distort the visible stance mix.")
    if no_author_ratio > 0.5:
        risks.append("Author metadata is sparse, limiting duplicate and cohort checks.")
    if max_sentiment_share >= 0.7:
        risks.append("One sentiment bucket dominates the visible comments; silent disagreement may be hidden.")
    if top_like_share >= 0.55:
        risks.append("Engagement is concentrated in top-liked comments, which can amplify a minority view.")

    if not risks:
        risks.append("Observed comments still represent people willing to speak, not the full reachable audience.")

    if count >= 100 and max_sentiment_share < 0.65:
        coverage = "medium_high"
        bias_level = "moderate"
    elif count >= 25:
        coverage = "medium"
        bias_level = "moderate_high" if len(risks) >= 3 else "moderate"
    else:
        coverage = "low"
        bias_level = "high"

    underrepresented = [
        "silent readers who consume but do not comment",
        "users who will see the story after secondary distribution",
        "risk-averse or compliance-sensitive users",
        "platform outsiders reached by reposts or summaries",
    ]
    if event.source.lower() in {"binance", "news", "feed", "hashtag"}:
        underrepresented.append("non-Binance audiences reacting on other social platforms")

    return SampleBiasAnalysis(
        bias_level=bias_level,
        coverage_level=coverage,
        risks=risks,
        likely_underrepresented_groups=underrepresented,
        rationale=(
            f"The observed sample has {count} comments and "
            f"{unique_authors or 'unknown'} unique authors; comment visibility is treated as partial coverage."
        ),
    )
