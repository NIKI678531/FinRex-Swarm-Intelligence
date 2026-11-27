"""Fuse observed analysis with agent augmentation."""

from __future__ import annotations

from typing import Dict, List

from .schema import AgentAugmentation, FusionResult, ObservedAnalysis, ReactionMode, SampleBiasAnalysis


def _risk_level(observed: ObservedAnalysis, sample_bias: SampleBiasAnalysis) -> str:
    neg = (observed.sentiment_distribution or {}).get("negative", 0)
    if sample_bias.bias_level in {"complete_gap", "high"} and observed.comment_count == 0:
        return "medium"
    if neg >= 0.55 or len(observed.risk_signals) >= 2:
        return "high"
    if neg >= 0.3 or observed.risk_signals or sample_bias.bias_level in {"high", "moderate_high"}:
        return "medium_high"
    return "medium"


def _adjusted_distribution(observed: ObservedAnalysis, agent_aug: AgentAugmentation) -> Dict[str, float]:
    dist = dict(observed.sentiment_distribution or {})
    if not dist:
        return {"positive": 0.32, "negative": 0.28, "neutral": 0.40}

    positive = dist.get("positive", 0.0)
    negative = dist.get("negative", 0.0)
    neutral = dist.get("neutral", 0.0)
    # Comment sections overrepresent expressive users. Pull extremes toward a
    # larger neutral/silent baseline, less aggressively when OASIS profiles exist.
    dampening = 0.22 if agent_aug.uses_oasis_profiles else 0.30
    positive = positive * (1 - dampening) + 0.32 * dampening
    negative = negative * (1 - dampening) + 0.28 * dampening
    neutral = neutral * (1 - dampening) + 0.40 * dampening
    total = max(positive + negative + neutral, 0.0001)
    return {
        "positive": round(positive / total, 4),
        "negative": round(negative / total, 4),
        "neutral": round(neutral / total, 4),
    }


def fuse_reaction_layers(
    mode: ReactionMode,
    observed: ObservedAnalysis,
    sample_bias: SampleBiasAnalysis,
    agent_aug: AgentAugmentation,
) -> FusionResult:
    caveats: List[str] = [
        "Observed means real supplied comment text only.",
        "Inferred combines observed data, sample-bias adjustment, and agent augmentation.",
        "Simulated is scenario output and must not be treated as measured public opinion.",
    ]
    if observed.comment_count == 0:
        caveats.append("No comment text was observed, so the run is agent-only.")
    if sample_bias.risks:
        caveats.extend(sample_bias.risks[:3])

    adjusted = _adjusted_distribution(observed, agent_aug)
    risk_level = _risk_level(observed, sample_bias)
    confidence = agent_aug.confidence
    if observed.comment_count >= 100:
        confidence += 0.16
    elif observed.comment_count >= 25:
        confidence += 0.08
    elif observed.comment_count == 0:
        confidence -= 0.08

    observed_layer = {
        "available": observed.comment_count > 0,
        "comment_count": observed.comment_count,
        # 真实评论条数（与 comment_count 等价，前端 dashboard 用更明确的字段名）
        "real_comment_count": observed.comment_count,
        "unique_authors": observed.unique_authors,
        "data_quality": observed.data_quality,
        "summary": observed.summary,
        "sentiment_distribution": observed.sentiment_distribution,
        "stance_distribution": observed.stance_distribution,
        "top_topics": observed.top_topics,
        "representative_comments": observed.representative_comments,
        "risk_signals": observed.risk_signals,
    }
    inferred_layer = {
        "mode": mode.value,
        "adjusted_sentiment_distribution": adjusted,
        "sample_bias": {
            "bias_level": sample_bias.bias_level,
            "coverage_level": sample_bias.coverage_level,
            "rationale": sample_bias.rationale,
            "underrepresented_groups": sample_bias.likely_underrepresented_groups,
        },
        "main_judgement": _main_judgement(adjusted, risk_level, observed.comment_count),
        "augmentation_source": agent_aug.agent_source,
    }
    simulated_layer = {
        "agent_source": agent_aug.agent_source,
        "uses_oasis_profiles": agent_aug.uses_oasis_profiles,
        "simulation_id": agent_aug.simulation_id,
        "segments": agent_aug.simulated_segments,
        "future_reactions": agent_aug.predicted_future_reactions,
        "silent_group_estimates": agent_aug.silent_group_estimates,
        "simulation_requirement_patch": agent_aug.simulation_requirement_patch,
    }

    return FusionResult(
        observed=observed_layer,
        inferred=inferred_layer,
        simulated=simulated_layer,
        overall_risk_level=risk_level,
        confidence=round(max(0.15, min(confidence, 0.86)), 2),
        caveats=caveats,
    )


def _main_judgement(dist: Dict[str, float], risk_level: str, observed_count: int) -> str:
    dominant = max(dist.items(), key=lambda item: item[1])[0] if dist else "neutral"
    if observed_count == 0:
        return f"Agent-only run: likely overall reaction is {dominant}, with {risk_level} propagation risk."
    return (
        f"After adjusting for silent and underrepresented audiences, the inferred overall reaction is "
        f"{dominant}, with {risk_level} propagation risk."
    )
