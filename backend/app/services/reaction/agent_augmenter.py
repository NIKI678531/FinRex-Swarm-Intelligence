"""Agent-style augmentation for missing or silent audience reactions."""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional

from ...config import Config
from .schema import AgentAugmentation, ObservedAnalysis, ReactionEvent, SampleBiasAnalysis


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_oasis_profiles(simulation_id: Optional[str]) -> List[Dict[str, Any]]:
    if not simulation_id:
        return []
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    profiles: Dict[str, Dict[str, Any]] = {}

    reddit_path = os.path.join(sim_dir, "reddit_profiles.json")
    data = _load_json(reddit_path)
    if isinstance(data, list):
        for row in data:
            uid = str(row.get("user_id") or row.get("id") or len(profiles))
            profiles[uid] = {**profiles.get(uid, {}), **row}

    twitter_path = os.path.join(sim_dir, "twitter_profiles.csv")
    if os.path.exists(twitter_path):
        with open(twitter_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = str(row.get("user_id") or row.get("id") or len(profiles))
                profiles[uid] = {**profiles.get(uid, {}), **row}

    index_path = os.path.join(sim_dir, "profile_index.json")
    index = _load_json(index_path)
    if isinstance(index, dict):
        for entry in index.get("entries", []):
            uid = str(entry.get("user_id") or "")
            if uid and uid in profiles:
                profiles[uid] = {**profiles[uid], **entry}
    return list(profiles.values())


def _dominant_sentiment(observed: ObservedAnalysis) -> str:
    dist = observed.sentiment_distribution or {}
    if not dist:
        return "neutral"
    return max(dist.items(), key=lambda item: item[1])[0]


def _event_risk(event: ReactionEvent) -> str:
    text = event.to_text().lower()
    high_terms = ["lawsuit", "sec", "regulator", "hack", "halt", "delist", "liquidation", "crash", "监管", "诉讼", "爆仓"]
    if any(term in text for term in high_terms):
        return "high"
    medium_terms = ["risk", "uncertain", "volatility", "rumor", "concern", "风险", "传闻", "波动"]
    if any(term in text for term in medium_terms):
        return "medium"
    return "low"


def _profile_segments(profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not profiles:
        return []
    risk_counter = Counter((p.get("risk_appetite") or p.get("risk_level") or "unknown") for p in profiles)
    profession_counter = Counter((p.get("profession") or p.get("source_entity_type") or "general") for p in profiles)
    total = len(profiles)
    return [
        {
            "segment": f"OASIS profiles: {risk}",
            "share": round(count / total, 4),
            "likely_reaction": _reaction_for_risk(risk),
            "basis": "Existing OASIS/persona profile distribution",
        }
        for risk, count in risk_counter.most_common(4)
    ] + [
        {
            "segment": f"Role cluster: {role}",
            "share": round(count / total, 4),
            "likely_reaction": "React through role-specific priors and preferred topics.",
            "basis": "Existing OASIS profile roles",
        }
        for role, count in profession_counter.most_common(2)
    ]


def _reaction_for_risk(risk: str) -> str:
    lower = str(risk).lower()
    if "high" in lower or "aggressive" in lower:
        return "More likely to amplify momentum narratives and challenge cautious interpretations."
    if "low" in lower or "conservative" in lower:
        return "More likely to wait for verification and react negatively to unresolved risk."
    if "mid" in lower or "medium" in lower:
        return "Likely to split between tactical interest and verification needs."
    return "Likely to respond based on headline framing and early comment cues."


def build_agent_augmentation(
    event: ReactionEvent,
    observed: ObservedAnalysis,
    sample_bias: SampleBiasAnalysis,
    simulation_id: Optional[str] = None,
) -> AgentAugmentation:
    profiles = _load_oasis_profiles(simulation_id)
    dominant = _dominant_sentiment(observed)
    event_risk = _event_risk(event)
    has_observed = observed.comment_count > 0

    segments = _profile_segments(profiles)
    if not segments:
        segments = [
            {
                "segment": "visible commenters",
                "share": 0.18 if has_observed else 0.0,
                "likely_reaction": f"Continue the observed {dominant} framing if early engagement rewards it.",
                "basis": "Observed comment sample" if has_observed else "No observed sample",
            },
            {
                "segment": "silent majority",
                "share": 0.46,
                "likely_reaction": "Mostly consume without posting; sentiment moves only after trusted summaries appear.",
                "basis": "Agent fallback for non-commenting users",
            },
            {
                "segment": "skeptical validators",
                "share": 0.16,
                "likely_reaction": "Ask for sources, numbers, counterexamples, and regulatory details before taking a side.",
                "basis": "Agent fallback for verification-seeking users",
            },
            {
                "segment": "momentum amplifiers",
                "share": 0.12,
                "likely_reaction": "Amplify simple bullish or bearish hooks if price or engagement moves in the same direction.",
                "basis": "Agent fallback for high-propagation users",
            },
            {
                "segment": "risk-sensitive users",
                "share": 0.08,
                "likely_reaction": "Overweight compliance, liquidity, and reputational downside.",
                "basis": "Agent fallback for defensive audience segments",
            },
        ]

    future = [
        {
            "horizon": "0-2h",
            "reaction": "Early reactions follow the headline and the first high-engagement comments.",
            "watch": "comment velocity, first KOL reposts, and sentiment skew",
        },
        {
            "horizon": "2-12h",
            "reaction": "Verification-seeking users enter; weak claims are challenged, while simple narratives spread further.",
            "watch": "source disputes, repeated talking points, and cross-platform reposts",
        },
        {
            "horizon": "12-48h",
            "reaction": "The discussion consolidates into a few stable camps unless new facts reset the frame.",
            "watch": "regulatory updates, price movement, and influencer summaries",
        },
    ]
    if event_risk == "high":
        future.insert(1, {
            "horizon": "risk trigger",
            "reaction": "High-risk language can pull silent users into defensive or critical reactions.",
            "watch": "legal, security, delisting, or liquidation confirmations",
        })

    silent_estimates = [
        {
            "group": group,
            "expected_difference_from_comments": "less expressive, slower to polarize, and more sensitive to trusted sources",
        }
        for group in sample_bias.likely_underrepresented_groups[:5]
    ]

    requirement_lines = [
        "Run event reaction simulation with explicit source separation.",
        f"Event title: {event.title or '(untitled)'}",
        f"Observed comments: {observed.comment_count}",
        f"Observed sentiment: {observed.sentiment_distribution or 'none'}",
        f"Sample bias: {sample_bias.bias_level} / {sample_bias.coverage_level}",
        "Simulate silent readers, late-arriving users, skeptics, momentum amplifiers, and risk-sensitive users.",
        "Output must label observed facts, inferred total reaction, and simulated future reaction separately.",
    ]

    confidence = 0.62 if profiles else 0.42
    if not has_observed:
        confidence -= 0.12
    return AgentAugmentation(
        agent_source="oasis_profiles" if profiles else "archetype_fallback",
        uses_oasis_profiles=bool(profiles),
        simulation_id=simulation_id,
        simulated_segments=segments,
        predicted_future_reactions=future,
        silent_group_estimates=silent_estimates,
        simulation_requirement_patch="\n".join(requirement_lines),
        confidence=round(max(0.2, min(confidence, 0.8)), 2),
    )
