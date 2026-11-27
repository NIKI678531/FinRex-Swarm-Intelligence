"""Data contracts for event reaction analysis.

The workflow always separates observed facts from inferred and simulated
judgements so downstream report prompts cannot blur those sources.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ReactionMode(str, Enum):
    AGENT_ONLY = "agent_only"
    OBSERVED_AUGMENTED = "observed_augmented"


class ReactionStatus(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReactionEvent:
    title: str = ""
    content: str = ""
    source: str = "manual"
    url: str = ""
    author: str = ""
    published_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_text(self, max_chars: int = 6000) -> str:
        parts = []
        if self.title:
            parts.append(self.title.strip())
        if self.content:
            parts.append(self.content.strip())
        text = "\n\n".join(p for p in parts if p)
        return text[:max_chars]


@dataclass
class ReactionComment:
    text: str
    source: str = "unknown"
    author: str = ""
    created_at: str = ""
    like_count: int = 0
    reply_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservedAnalysis:
    comment_count: int = 0
    unique_authors: int = 0
    sentiment_distribution: Dict[str, float] = field(default_factory=dict)
    stance_distribution: Dict[str, float] = field(default_factory=dict)
    top_topics: List[Dict[str, Any]] = field(default_factory=list)
    representative_comments: List[Dict[str, Any]] = field(default_factory=list)
    risk_signals: List[str] = field(default_factory=list)
    data_quality: str = "none"
    summary: str = ""


@dataclass
class SampleBiasAnalysis:
    bias_level: str = "unknown"
    coverage_level: str = "unknown"
    risks: List[str] = field(default_factory=list)
    likely_underrepresented_groups: List[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class AgentAugmentation:
    agent_source: str = "archetype_fallback"
    uses_oasis_profiles: bool = False
    simulation_id: Optional[str] = None
    simulated_segments: List[Dict[str, Any]] = field(default_factory=list)
    predicted_future_reactions: List[Dict[str, Any]] = field(default_factory=list)
    silent_group_estimates: List[Dict[str, Any]] = field(default_factory=list)
    simulation_requirement_patch: str = ""
    confidence: float = 0.35


@dataclass
class FusionResult:
    observed: Dict[str, Any] = field(default_factory=dict)
    inferred: Dict[str, Any] = field(default_factory=dict)
    simulated: Dict[str, Any] = field(default_factory=dict)
    overall_risk_level: str = "medium"
    confidence: float = 0.4
    caveats: List[str] = field(default_factory=list)


@dataclass
class ReactionAnalysisRun:
    run_id: str
    mode: ReactionMode
    status: ReactionStatus
    created_at: str
    updated_at: str
    event: ReactionEvent
    dimensions: List[str] = field(default_factory=list)
    simulation_id: Optional[str] = None
    comments_count: int = 0
    selected_articles_count: int = 0
    observed: Optional[ObservedAnalysis] = None
    sample_bias: Optional[SampleBiasAnalysis] = None
    agent_augmentation: Optional[AgentAugmentation] = None
    fusion: Optional[FusionResult] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value if isinstance(self.mode, ReactionMode) else self.mode
        data["status"] = self.status.value if isinstance(self.status, ReactionStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReactionAnalysisRun":
        event_data = data.get("event") or {}
        return cls(
            run_id=data["run_id"],
            mode=ReactionMode(data.get("mode", ReactionMode.AGENT_ONLY.value)),
            status=ReactionStatus(data.get("status", ReactionStatus.CREATED.value)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            event=ReactionEvent(**event_data),
            dimensions=data.get("dimensions") or [],
            simulation_id=data.get("simulation_id"),
            comments_count=data.get("comments_count", 0),
            selected_articles_count=data.get("selected_articles_count", 0),
            observed=ObservedAnalysis(**data["observed"]) if data.get("observed") else None,
            sample_bias=SampleBiasAnalysis(**data["sample_bias"]) if data.get("sample_bias") else None,
            agent_augmentation=AgentAugmentation(**data["agent_augmentation"])
            if data.get("agent_augmentation") else None,
            fusion=FusionResult(**data["fusion"]) if data.get("fusion") else None,
            error=data.get("error"),
            metadata=data.get("metadata") or {},
        )
