"""Load OASIS action streams for report dashboard modeling."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import Config


TEXT_FIELDS = (
    "content",
    "text",
    "body",
    "query",
    "post_content",
    "comment_content",
    "original_content",
    "quote_content",
    "result",
)


@dataclass
class OasisActionRecord:
    action_id: str
    raw: Dict[str, Any]
    platform: str
    line_no: int
    round_num: int = 0
    timestamp: str = ""
    event_type: str = ""
    simulated_hour: Optional[float] = None
    actions_count: int = 0
    agent_id: Optional[int] = None
    agent_name: str = ""
    action_type: str = ""
    action_args: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    text: str = ""

    @property
    def is_event(self) -> bool:
        return bool(self.event_type)

    @property
    def is_action(self) -> bool:
        return not self.event_type and bool(self.action_type)


@dataclass
class OasisActionBundle:
    simulation_id: str
    simulation_dir: str
    records: List[OasisActionRecord] = field(default_factory=list)
    actions: List[OasisActionRecord] = field(default_factory=list)
    round_events: List[OasisActionRecord] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    run_state: Dict[str, Any] = field(default_factory=dict)
    files_read: int = 0
    missing_files: List[str] = field(default_factory=list)
    bad_lines: int = 0

    @property
    def has_any_stream(self) -> bool:
        return bool(self.records or self.files_read)


class OasisActionLoader:
    """Read OASIS platform action logs without depending on the runner process."""

    PLATFORMS = ("twitter", "reddit")

    @classmethod
    def load(cls, simulation_id: Optional[str]) -> OasisActionBundle:
        sim_id = simulation_id or ""
        sim_dir = os.path.abspath(os.path.join(Config.OASIS_SIMULATION_DATA_DIR, sim_id)) if sim_id else ""
        bundle = OasisActionBundle(simulation_id=sim_id, simulation_dir=sim_dir)
        if not sim_id or not os.path.isdir(sim_dir):
            return bundle

        bundle.config = cls._read_json(os.path.join(sim_dir, "simulation_config.json"))
        bundle.run_state = cls._read_json(os.path.join(sim_dir, "run_state.json"))

        paths = [(platform, os.path.join(sim_dir, platform, "actions.jsonl")) for platform in cls.PLATFORMS]
        paths.append(("", os.path.join(sim_dir, "actions.jsonl")))

        for default_platform, path in paths:
            if not os.path.exists(path):
                bundle.missing_files.append(path)
                continue
            bundle.files_read += 1
            cls._read_jsonl(path, default_platform or "unknown", bundle)

        bundle.actions = [record for record in bundle.records if record.is_action]
        bundle.round_events = [record for record in bundle.records if record.is_event]
        return bundle

    @classmethod
    def _read_jsonl(cls, path: str, default_platform: str, bundle: OasisActionBundle) -> None:
        with open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    bundle.bad_lines += 1
                    continue
                if not isinstance(data, dict):
                    bundle.bad_lines += 1
                    continue
                platform = data.get("platform") or default_platform
                record = cls._record_from_dict(data, platform, line_no)
                bundle.records.append(record)

    @classmethod
    def _record_from_dict(cls, data: Dict[str, Any], platform: str, line_no: int) -> OasisActionRecord:
        action_args = data.get("action_args") if isinstance(data.get("action_args"), dict) else {}
        event_type = str(data.get("event_type") or "")
        round_num = int(data.get("round") or data.get("round_num") or 0)
        action_type = str(data.get("action_type") or "")
        simulated_value = data.get("simulated_hour") if "simulated_hour" in data else data.get("simulated_hours")
        action_id = f"{platform}:{line_no}:{round_num}:{event_type or action_type or 'event'}"
        return OasisActionRecord(
            action_id=action_id,
            raw=data,
            platform=platform,
            line_no=line_no,
            round_num=round_num,
            timestamp=str(data.get("timestamp") or ""),
            event_type=event_type,
            simulated_hour=cls._float_or_none(simulated_value),
            actions_count=int(data.get("actions_count") or data.get("total_actions") or 0),
            agent_id=data.get("agent_id"),
            agent_name=str(data.get("agent_name") or ""),
            action_type=action_type,
            action_args=action_args,
            success=bool(data.get("success", True)),
            text=cls.extract_text(data),
        )

    @staticmethod
    def extract_text(data: Dict[str, Any]) -> str:
        chunks: List[str] = []
        action_args = data.get("action_args") if isinstance(data.get("action_args"), dict) else {}
        for source in (data, action_args):
            for field in TEXT_FIELDS:
                value = source.get(field)
                if isinstance(value, str) and value.strip():
                    chunks.append(value.strip())
        seen = set()
        out: List[str] = []
        for chunk in chunks:
            if chunk not in seen:
                seen.add(chunk)
                out.append(chunk)
        return "\n".join(out)

    @staticmethod
    def _read_json(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
