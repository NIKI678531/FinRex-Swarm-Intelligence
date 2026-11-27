"""Time Pulse Model for OASIS-backed report dashboards."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .hf_inference import HFInferenceClient, top_label
from .oasis_action_loader import OasisActionBundle, OasisActionLoader, OasisActionRecord


POSITIVE_TERMS = {
    "bull", "bullish", "buy", "bought", "rally", "breakout", "growth", "upside",
    "support", "positive", "rebound", "recover", "看多", "利好", "上涨", "买入", "支持", "反弹",
}
NEGATIVE_TERMS = {
    "bear", "bearish", "sell", "dump", "crash", "weak", "miss", "downside", "fear",
    "panic", "negative", "drop", "看空", "利空", "下跌", "卖出", "反对", "恐慌", "崩",
}
RISK_TERMS = {
    "risk", "regulator", "lawsuit", "sec", "hack", "halt", "delist", "liquidation",
    "fraud", "scam", "监管", "诉讼", "爆仓", "黑客", "退市", "风险", "争议", "质疑", "合规",
}
EMOTION_TERMS = {
    "angry", "rage", "outrage", "fear", "panic", "concern", "worry", "hate",
    "愤怒", "恐慌", "担心", "焦虑", "抵制", "离谱", "担忧",
}
ACTIVE_ACTIONS = {"CREATE_POST", "CREATE_COMMENT", "QUOTE_POST", "REPOST"}
NEGATIVE_ACTIONS = {"DISLIKE_POST", "DISLIKE_COMMENT", "MUTE"}
POSITIVE_ACTIONS = {"LIKE_POST", "LIKE_COMMENT", "FOLLOW", "REPOST"}


def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now().replace(microsecond=0)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now().replace(microsecond=0)


def _contains(text: str, terms: Iterable[str]) -> int:
    lower = (text or "").lower()
    return sum(1 for term in terms if term.lower() in lower)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _mean(values: List[float]) -> float:
    return sum(values) / max(1, len(values))


def _std(values: List[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = _mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


class TimePulseModel:
    """Build a dynamic report dashboard from OASIS action events."""

    @classmethod
    def build_dashboard(
        cls,
        report: Dict[str, Any],
        topics: List[Dict[str, Any]],
        fallback_sentiment: float = 0.0,
        fallback_active_personas: int = 0,
    ) -> Optional[Dict[str, Any]]:
        simulation_id = report.get("simulation_id")
        if not simulation_id:
            return None

        bundle = OasisActionLoader.load(simulation_id)
        if not bundle.has_any_stream:
            return None

        start = _parse_dt(report.get("created_at") or report.get("completed_at"))
        minutes_per_round = cls._minutes_per_round(bundle)
        bins = cls._build_bins(bundle, start, minutes_per_round)
        if not bins:
            return None

        cls._score_bins(bins, fallback_sentiment)
        pulse_events = cls._detect_pulses(bins, topics, report)
        key_events = cls._key_events(pulse_events)
        model_status = cls._model_status(bundle, bins)

        source_status = {
            "source": "oasis_actions",
            "is_dynamic": any(item["volume"] > 0 for item in bins),
            "simulation_id": simulation_id,
            "files_read": bundle.files_read,
            "actions_count": len(bundle.actions),
            "round_event_count": len(bundle.round_events),
            "bad_lines": bundle.bad_lines,
            "fallback_reason": "" if any(item["volume"] > 0 for item in bins) else "oasis_stream_has_no_positive_volume",
            "model_pipeline": [
                "oasis_action_loader",
                "local_financial_sentiment_rules",
                "local_emotion_risk_rules",
                "kleinberg_style_burst_fallback",
                "optional_hf_financial_sentiment",
                "optional_hf_multilingual_emotion_license_guard",
                "optional_darts_forecast_provider_disabled",
                "optional_hawkes_provider_disabled",
            ],
            "model_status": model_status,
        }

        total_volume = sum(item["volume"] for item in bins)
        peak = max(bins, key=lambda item: item["volume"])
        sentiment_values = [item["sentiment"] for item in bins]
        active_personas = max(
            fallback_active_personas,
            max((item["active_personas"] for item in bins), default=0),
        )
        return {
            "kpis": {
                "total_volume": total_volume,
                "peak_time": peak["t"],
                "sentiment_avg": round(_mean(sentiment_values), 2),
                "active_personas": active_personas,
            },
            "timeline": bins,
            "pulse_events": pulse_events,
            "key_events": key_events,
            "source_status": source_status,
        }

    @classmethod
    def _minutes_per_round(cls, bundle: OasisActionBundle) -> float:
        time_config = bundle.config.get("time_config") if isinstance(bundle.config.get("time_config"), dict) else {}
        value = time_config.get("minutes_per_round") or 60
        try:
            return max(float(value), 1.0)
        except (TypeError, ValueError):
            return 60.0

    @classmethod
    def _build_bins(cls, bundle: OasisActionBundle, start: datetime, minutes_per_round: float) -> List[Dict[str, Any]]:
        round_to_hour: Dict[int, float] = {}
        round_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for event in bundle.round_events:
            if event.event_type == "round_start" and event.simulated_hour is not None:
                round_to_hour[event.round_num] = float(event.simulated_hour)
            if event.event_type == "round_end":
                round_counts[event.round_num][event.platform] += int(event.actions_count or 0)

        actions_by_round: Dict[int, List[OasisActionRecord]] = defaultdict(list)
        for action in bundle.actions:
            actions_by_round[action.round_num].append(action)

        round_nums = sorted(set(round_counts.keys()) | set(actions_by_round.keys()) | set(round_to_hour.keys()))
        bins: List[Dict[str, Any]] = []
        for round_num in round_nums:
            actions = actions_by_round.get(round_num, [])
            real_platform_counts: Dict[str, int] = defaultdict(int)
            active_agents = set()
            action_types: Dict[str, int] = defaultdict(int)
            texts: List[str] = []
            action_ids: List[str] = []
            for action in actions:
                real_platform_counts[action.platform] += 1
                action_types[action.action_type] += 1
                action_ids.append(action.action_id)
                if action.agent_id is not None:
                    active_agents.add(action.agent_id)
                if action.text:
                    texts.append(action.text)

            event_platform_counts = dict(round_counts.get(round_num, {}))
            platform_counts = dict(real_platform_counts)
            for platform, count in event_platform_counts.items():
                platform_counts[platform] = max(platform_counts.get(platform, 0), count)

            volume = max(sum(real_platform_counts.values()), sum(event_platform_counts.values()))
            x = round((round_num * minutes_per_round) / 60.0, 3)
            simulated_hour = round_to_hour.get(round_num, x)
            bins.append({
                "t": (start + timedelta(hours=x)).isoformat(),
                "x": x,
                "round": round_num,
                "simulated_hour": simulated_hour,
                "volume": int(volume),
                "sentiment": 0.0,
                "emotion_intensity": 0.0,
                "risk_intensity": 0.0,
                "pulse_score": 0.0,
                "burst_state": "baseline",
                "platform_breakdown": platform_counts,
                "active_personas": len(active_agents),
                "action_types": dict(action_types),
                "trigger_action_ids": action_ids[:8],
                "sample_text": cls._sample_text(texts),
            })
        return bins

    @classmethod
    def _score_bins(cls, bins: List[Dict[str, Any]], fallback_sentiment: float) -> None:
        volumes = [float(item["volume"]) for item in bins]
        active = [float(item["active_personas"]) for item in bins]
        mean_volume = _mean(volumes)
        std_volume = _std(volumes)
        mean_active = _mean(active)
        std_active = _std(active)
        previous_volume = 0.0
        previous_sentiment = fallback_sentiment

        raw_scores: List[float] = []
        for item in bins:
            sentiment = cls._sentiment_for_bin(item, fallback_sentiment)
            emotion = cls._emotion_for_bin(item)
            risk = cls._risk_for_bin(item)
            velocity = float(item["volume"]) - previous_volume
            sentiment_shift = abs(sentiment - previous_sentiment)
            platform_spread = min(1.0, len([v for v in (item.get("platform_breakdown") or {}).values() if v > 0]) / 2.0)
            z_volume = max(0.0, (float(item["volume"]) - mean_volume) / std_volume) if std_volume > 0 else 0.0
            z_velocity = max(0.0, velocity / std_volume) if std_volume > 0 else 0.0
            z_active = max(0.0, (float(item["active_personas"]) - mean_active) / std_active) if std_active > 0 else 0.0
            score = (
                0.30 * z_volume
                + 0.18 * z_velocity
                + 0.12 * z_active
                + 0.12 * sentiment_shift
                + 0.12 * risk
                + 0.08 * emotion
                + 0.08 * platform_spread
            )
            item["sentiment"] = round(sentiment, 2)
            item["emotion_intensity"] = round(emotion, 2)
            item["risk_intensity"] = round(risk, 2)
            item["velocity"] = int(velocity)
            item["pulse_score"] = round(score, 3)
            raw_scores.append(score)
            previous_volume = float(item["volume"])
            previous_sentiment = sentiment

        avg_score = _mean(raw_scores)
        std_score = _std(raw_scores)
        for item in bins:
            if std_volume > 0 and item["volume"] >= mean_volume + 2 * std_volume:
                item["burst_state"] = "burst"
            elif std_score > 0 and item["pulse_score"] >= avg_score + std_score:
                item["burst_state"] = "watch"

    @classmethod
    def _sentiment_for_bin(cls, item: Dict[str, Any], fallback: float) -> float:
        text = item.get("sample_text") or ""
        pos = _contains(text, POSITIVE_TERMS)
        neg = _contains(text, NEGATIVE_TERMS)
        action_types = item.get("action_types") or {}
        pos += sum(count for action, count in action_types.items() if action in POSITIVE_ACTIONS) * 0.35
        neg += sum(count for action, count in action_types.items() if action in NEGATIVE_ACTIONS) * 0.45
        if not text and pos == 0 and neg == 0:
            return float(fallback or 0.0)
        return _clamp((pos - neg) / max(1.0, pos + neg + 1.0), -1.0, 1.0)

    @classmethod
    def _emotion_for_bin(cls, item: Dict[str, Any]) -> float:
        text = item.get("sample_text") or ""
        action_types = item.get("action_types") or {}
        expressive = sum(count for action, count in action_types.items() if action in ACTIVE_ACTIONS)
        score = _contains(text, EMOTION_TERMS) * 0.25 + min(0.45, expressive * 0.08)
        return _clamp(score, 0.0, 1.0)

    @classmethod
    def _risk_for_bin(cls, item: Dict[str, Any]) -> float:
        text = item.get("sample_text") or ""
        action_types = item.get("action_types") or {}
        negative_actions = sum(count for action, count in action_types.items() if action in NEGATIVE_ACTIONS)
        score = _contains(text, RISK_TERMS) * 0.22 + min(0.42, negative_actions * 0.12)
        return _clamp(score, 0.0, 1.0)

    @classmethod
    def _detect_pulses(cls, bins: List[Dict[str, Any]], topics: List[Dict[str, Any]], report: Dict[str, Any]) -> List[Dict[str, Any]]:
        scored = [item for item in bins if item["volume"] > 0 or item["pulse_score"] > 0]
        bursts = [item for item in scored if item.get("burst_state") == "burst"]
        if not bursts:
            bursts = cls._local_maxima(scored)
        if not bursts:
            return []

        bursts = sorted(bursts, key=lambda item: (item.get("pulse_score") or 0, item.get("volume") or 0), reverse=True)[:6]
        bursts.sort(key=lambda item: item.get("x") or 0)
        out: List[Dict[str, Any]] = []
        for index, item in enumerate(bursts, start=1):
            topic = topics[(index - 1) % len(topics)] if topics else {}
            intensity = max(float(item.get("pulse_score") or 0), float(item.get("risk_intensity") or 0), float(topic.get("heat") or 0.5))
            out.append({
                "id": f"pulse_{report.get('report_id') or 'report'}_{index}",
                "t": item.get("t"),
                "x": item.get("x"),
                "round": item.get("round"),
                "simulated_hour": item.get("simulated_hour"),
                "volume": item.get("volume", 0),
                "intensity": round(_clamp(intensity, 0.0, 1.0), 2),
                "title": topic.get("title") or f"OASIS 脉冲 Round {item.get('round')}",
                "summary": topic.get("summary") or cls._pulse_summary(item),
                "source_layer": topic.get("source_layer") or "Simulated",
                "trigger_action_ids": item.get("trigger_action_ids") or [],
                "topic_id": topic.get("id"),
                "model_scores": {
                    "pulse_score": item.get("pulse_score", 0),
                    "risk_intensity": item.get("risk_intensity", 0),
                    "emotion_intensity": item.get("emotion_intensity", 0),
                    "sentiment": item.get("sentiment", 0),
                    "burst_state": item.get("burst_state", "baseline"),
                },
            })
        return out

    @classmethod
    def _local_maxima(cls, scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not scored:
            return []
        out: List[Dict[str, Any]] = []
        for index, item in enumerate(scored):
            left = scored[index - 1]["volume"] if index > 0 else -1
            right = scored[index + 1]["volume"] if index + 1 < len(scored) else -1
            if item["volume"] >= left and item["volume"] >= right:
                out.append(item)
        return out or sorted(scored, key=lambda item: item.get("volume") or 0, reverse=True)[:4]

    @staticmethod
    def _key_events(pulse_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "t": pulse.get("t"),
                "label": pulse.get("title") or "OASIS 脉冲",
                "weight": pulse.get("intensity", 0.5),
                "post_ids": pulse.get("trigger_action_ids") or [],
                "pulse_id": pulse.get("id"),
                "action_ids": pulse.get("trigger_action_ids") or [],
            }
            for pulse in pulse_events
        ]

    @staticmethod
    def _pulse_summary(item: Dict[str, Any]) -> str:
        return (
            f"Round {item.get('round')} 声量 {item.get('volume')}，"
            f"情绪 {item.get('sentiment')}，风险强度 {item.get('risk_intensity')}。"
        )

    @staticmethod
    def _sample_text(texts: List[str], limit: int = 900) -> str:
        out = " ".join(text.strip() for text in texts if text.strip())
        return out[:limit]

    @classmethod
    def _model_status(cls, bundle: OasisActionBundle, bins: List[Dict[str, Any]]) -> Dict[str, Any]:
        texts = [item.get("sample_text") for item in bins if item.get("sample_text")]
        client = HFInferenceClient()
        financial = client.classify_financial(texts[: client.max_items]) if texts else {
            "task": "financial_sentiment",
            "model": client.financial_model,
            "status": "skipped",
            "reason": "no action text",
            "items": [],
        }
        emotion = client.classify_emotion(texts[: client.max_items]) if texts else {
            "task": "emotion",
            "model": client.emotion_model,
            "status": "skipped",
            "reason": "no action text",
            "items": [],
        }
        top_fin = top_label(financial.get("items", [None])[0]) if financial.get("items") else None
        top_emo = top_label(emotion.get("items", [None])[0]) if emotion.get("items") else None
        return {
            "financial_sentiment": financial,
            "emotion": emotion,
            "top_financial_label": top_fin,
            "top_emotion_label": top_emo,
            "burst": {"status": "ok", "method": "kleinberg_style_local_burst", "dependency": "local"},
            "forecast": {"status": "disabled", "provider": "darts_optional"},
            "cascade": {"status": "proxy", "provider": "pyhawkes_or_tick_optional"},
            "records": {"actions": len(bundle.actions), "round_events": len(bundle.round_events)},
        }

