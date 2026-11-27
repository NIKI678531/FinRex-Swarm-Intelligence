"""Persistence and orchestration for reaction analysis runs."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...config import Config
from ...utils.logger import get_logger
from .agent_augmenter import build_agent_augmentation
from .comment_normalizer import normalize_payload
from .fusion_engine import fuse_reaction_layers
from .observed_analyzer import analyze_observed
from .sample_bias_analyzer import analyze_sample_bias
from .schema import ReactionAnalysisRun, ReactionMode, ReactionStatus

logger = get_logger("finrex.reaction.run_manager")


class ReactionRunManager:
    RUNS_DIR = os.path.join(Config.UPLOAD_FOLDER, "reactions")

    @classmethod
    def _ensure_runs_dir(cls) -> None:
        os.makedirs(cls.RUNS_DIR, exist_ok=True)

    @classmethod
    def _run_dir(cls, run_id: str) -> str:
        return os.path.join(cls.RUNS_DIR, run_id)

    @classmethod
    def _run_path(cls, run_id: str) -> str:
        return os.path.join(cls._run_dir(run_id), "run.json")

    @classmethod
    def save_run(cls, run: ReactionAnalysisRun) -> None:
        cls._ensure_runs_dir()
        os.makedirs(cls._run_dir(run.run_id), exist_ok=True)
        run.touch()
        with open(cls._run_path(run.run_id), "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def get_run(cls, run_id: str) -> Optional[ReactionAnalysisRun]:
        path = cls._run_path(run_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return ReactionAnalysisRun.from_dict(json.load(f))

    @classmethod
    def list_runs(cls, limit: int = 50) -> List[ReactionAnalysisRun]:
        cls._ensure_runs_dir()
        runs: List[ReactionAnalysisRun] = []
        for run_id in os.listdir(cls.RUNS_DIR):
            run = cls.get_run(run_id)
            if run:
                runs.append(run)
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]

    @classmethod
    def analyze(cls, payload: Dict[str, Any]) -> ReactionAnalysisRun:
        event, comments = normalize_payload(payload)
        selected_articles = payload.get("selected_articles") or payload.get("articles") or []
        simulation_id = payload.get("simulation_id") or payload.get("existing_simulation_id")
        dimensions = payload.get("dimensions") or ["sentiment", "persona", "cluster", "risk"]
        mode = ReactionMode.OBSERVED_AUGMENTED if comments else ReactionMode.AGENT_ONLY
        now = datetime.now().isoformat()
        run = ReactionAnalysisRun(
            run_id=f"react_{uuid.uuid4().hex[:12]}",
            mode=mode,
            status=ReactionStatus.CREATED,
            created_at=now,
            updated_at=now,
            event=event,
            dimensions=dimensions,
            simulation_id=simulation_id,
            comments_count=len(comments),
            selected_articles_count=len(selected_articles) if isinstance(selected_articles, list) else 0,
            metadata={
                "input_source": payload.get("source") or event.source,
                "has_real_comments": bool(comments),
                "selected_article_ids": event.metadata.get("selected_article_ids", []),
            },
        )
        cls.save_run(run)

        try:
            run.status = ReactionStatus.PROCESSING
            cls.save_run(run)

            observed = analyze_observed(event, comments)
            bias = analyze_sample_bias(event, comments, observed)
            augmentation = build_agent_augmentation(
                event=event,
                observed=observed,
                sample_bias=bias,
                simulation_id=simulation_id,
            )
            fusion = fuse_reaction_layers(mode, observed, bias, augmentation)

            run.observed = observed
            run.sample_bias = bias
            run.agent_augmentation = augmentation
            run.fusion = fusion
            run.status = ReactionStatus.COMPLETED
            cls.save_run(run)
            logger.info("Reaction analysis completed: %s mode=%s comments=%s", run.run_id, mode.value, len(comments))
        except Exception as exc:
            logger.exception("Reaction analysis failed: %s", run.run_id)
            run.status = ReactionStatus.FAILED
            run.error = str(exc)
            cls.save_run(run)
        return run

    @classmethod
    def build_report_context(cls, run: ReactionAnalysisRun) -> str:
        fusion = run.fusion
        if not fusion:
            return "Reaction analysis has no completed fusion result."
        return "\n".join([
            "# Reaction Analysis Context",
            f"Run ID: {run.run_id}",
            f"Mode: {run.mode.value}",
            f"Event: {run.event.title or '(untitled)'}",
            "",
            "## Observed",
            json.dumps(fusion.observed, ensure_ascii=False, indent=2),
            "",
            "## Inferred",
            json.dumps(fusion.inferred, ensure_ascii=False, indent=2),
            "",
            "## Simulated",
            json.dumps(fusion.simulated, ensure_ascii=False, indent=2),
            "",
            "## Guardrail",
            "Observed facts, inferred judgements, and simulated outcomes must remain clearly labelled.",
        ])
