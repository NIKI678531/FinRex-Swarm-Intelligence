"""Public Opinion Layer aggregation for unified reports."""

from __future__ import annotations

from typing import Any, Dict, List

from .hf_inference import HFInferenceClient, top_label
from .report_agent import ReportManager
from .report_v2_adapter import ReportV2Adapter


class PublicOpinionService:
    @classmethod
    def get_public_opinion(cls, report_id: str, regenerate: bool = False) -> Dict[str, Any]:
        report = ReportManager.get_report(report_id)
        if not report:
            raise ValueError(f"report {report_id} not found")

        if not cls._is_usable_report(report):
            replacement = cls._replacement_report(report)
            if replacement:
                return cls._recovery_payload(report, replacement)

        bundle = ReportV2Adapter.build(report)
        report_dict = report.to_dict()
        opinion = bundle.get("public_opinion") or {}
        dashboard = bundle.get("dashboard") or {}
        topics = cls._topics(opinion)
        cls._attach_remote_labels(topics)

        reaction = bundle.get("reaction") or {}
        observed_fusion = (reaction.get("fusion") or {}).get("observed") or {}
        # 真实评论数（来自用户粘贴 / 文章评论 / Binance 评论原文）
        real_comment_count = int(observed_fusion.get("real_comment_count")
                                  or observed_fusion.get("comment_count") or 0)

        return {
            "report_id": report_id,
            "simulation_id": report_dict.get("simulation_id"),
            "summary": cls._summary(report_dict, dashboard, opinion, topics, real_comment_count),
            "layers": cls._layers(topics, opinion, reaction),
            "pulses": cls._pulses(dashboard, topics),
            "topics": topics,
            "stakeholders": opinion.get("stakeholders") or [],
            "evidence": cls._evidence(topics),
            "model_status": cls._model_status(topics, dashboard),
            # 顶层暴露真实评论数与主题覆盖率，前端 dashboard 直接消费
            "real_comment_count": real_comment_count,
            "topic_coverage": cls._topic_coverage(topics),
            # 热点产品预测（来自 strategy.product_matches + 报告频次）
            "hot_products": opinion.get("hot_products") or [],
        }

    @staticmethod
    def _is_usable_report(report) -> bool:
        return bool(
            report
            and getattr(report.status, "value", str(report.status)) == "completed"
            and (report.markdown_content or report.outline)
        )

    @classmethod
    def _replacement_report(cls, report):
        preferred_types = [getattr(report, "report_type", None), "narrative", None]
        seen = set()
        for report_type in preferred_types:
            if report_type in seen:
                continue
            seen.add(report_type)
            candidate = ReportManager.get_report_by_simulation(report.simulation_id, report_type)
            if candidate and candidate.report_id != report.report_id and cls._is_usable_report(candidate):
                return candidate
        return None

    @classmethod
    def _recovery_payload(cls, report, replacement) -> Dict[str, Any]:
        report_dict = report.to_dict()
        replacement_dict = replacement.to_dict()
        return {
            "report_id": report.report_id,
            "simulation_id": report.simulation_id,
            "replacement_report_id": replacement.report_id,
            "replacement_report_type": replacement.report_type,
            "summary": {
                "text": "The requested report failed before content was generated; a completed replacement report is available for this simulation.",
                "status": report_dict.get("status"),
                "generated_at": report_dict.get("completed_at") or report_dict.get("created_at"),
                "total_volume": 0,
                "real_comment_count": 0,
                "sentiment_net": 0,
                "risk_level": "unknown",
                "confidence": 0,
                "data_coverage": {"observed": 0, "inferred": 0, "simulated": 0},
                "recoverable": True,
                "replacement_report_id": replacement.report_id,
                "replacement_status": replacement_dict.get("status"),
            },
            "layers": {"observed": {}, "inferred": {}, "simulated": {}},
            "pulses": [],
            "topics": [],
            "stakeholders": [],
            "evidence": [],
            "model_status": {"recovery": {"status": "replacement_available"}},
            "real_comment_count": 0,
            "topic_coverage": {"total_topics": 0, "observed_ratio": 0, "inferred_ratio": 0, "simulated_ratio": 0},
            "hot_products": [],
        }

    @classmethod
    def _topics(cls, opinion: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for index, topic in enumerate(opinion.get("hot_topics") or [], start=1):
            layer = topic.get("source_layer") or "Inferred"
            out.append({
                "id": topic.get("id") or f"topic_{index}",
                "title": topic.get("title") or f"Topic {index}",
                "summary": topic.get("summary") or "",
                "source_layer": layer,
                "heat": topic.get("heat", 0.5),
                "confidence": topic.get("confidence", 0.5),
                "stance": topic.get("stance", "neutral"),
                "keywords": topic.get("keywords") or [],
                "driver_scores": topic.get("driver_scores") or {},
                "evidence_ids": topic.get("evidence_ids") or [],
                "evidence": topic.get("evidence") or [],
                # 预测字段
                "predicted_intensity": topic.get("predicted_intensity"),
                "horizon": topic.get("horizon"),
                "related_products": topic.get("related_products") or [],
            })
        return out

    @classmethod
    def _attach_remote_labels(cls, topics: List[Dict[str, Any]]) -> None:
        texts = [". ".join([topic.get("title", ""), topic.get("summary", "")]).strip() for topic in topics]
        client = HFInferenceClient()
        financial = client.classify_financial(texts)
        emotion = client.classify_emotion(texts)

        for index, topic in enumerate(topics):
            fin_label = None
            emo_label = None
            if financial.get("status") == "ok" and index < len(financial.get("items") or []):
                fin_label = top_label(financial["items"][index])
            if emotion.get("status") == "ok" and index < len(emotion.get("items") or []):
                emo_label = top_label(emotion["items"][index])
            topic["sentiment_label"] = (fin_label or {}).get("label") or cls._rule_sentiment(topic.get("stance"))
            topic["sentiment_score"] = round(float((fin_label or {}).get("score") or topic.get("confidence") or 0), 3)
            topic["emotion_label"] = (emo_label or {}).get("label") or cls._rule_emotion(topic)
            topic["model_status"] = {"financial_sentiment": financial, "emotion": emotion}

    @classmethod
    def _rule_sentiment(cls, stance: str) -> str:
        return {"bull": "positive", "bear": "negative", "contrarian": "mixed"}.get(stance or "", "neutral")

    @classmethod
    def _rule_emotion(cls, topic: Dict[str, Any]) -> str:
        drivers = topic.get("driver_scores") or {}
        if drivers.get("risk", 0) >= 0.45:
            return "concern"
        if drivers.get("opportunity", 0) >= 0.45:
            return "interest"
        if drivers.get("engagement", 0) >= 0.55:
            return "attention"
        return "neutral"

    @classmethod
    def _summary(
        cls,
        report: Dict[str, Any],
        dashboard: Dict[str, Any],
        opinion: Dict[str, Any],
        topics: List[Dict[str, Any]],
        real_comment_count: int = 0,
    ) -> Dict[str, Any]:
        kpis = dashboard.get("kpis") or {}
        layer_counts = cls._layer_counts(topics)
        coverage_total = max(1, sum(layer_counts.values()))
        return {
            "text": opinion.get("summary") or (report.get("outline") or {}).get("summary") or "",
            "status": report.get("status"),
            "generated_at": report.get("completed_at") or report.get("created_at"),
            "total_volume": kpis.get("total_volume", 0),
            # 真实评论数（区别于推断/模拟主题覆盖率）
            "real_comment_count": real_comment_count,
            "sentiment_net": kpis.get("sentiment_avg", 0),
            "risk_level": cls._risk_level(topics),
            "confidence": round(sum(float(t.get("confidence") or 0) for t in topics) / max(1, len(topics)), 2),
            "data_coverage": {
                "observed": round(layer_counts["Observed"] / coverage_total, 2),
                "inferred": round(layer_counts["Inferred"] / coverage_total, 2),
                "simulated": round(layer_counts["Simulated"] / coverage_total, 2),
            },
        }

    @classmethod
    def _topic_coverage(cls, topics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """主题覆盖率：按 source_layer 分布，与真实评论数解耦。"""
        counts = cls._layer_counts(topics)
        total = max(1, sum(counts.values()))
        return {
            "total_topics": sum(counts.values()),
            "observed_ratio": round(counts.get("Observed", 0) / total, 4),
            "inferred_ratio": round(counts.get("Inferred", 0) / total, 4),
            "simulated_ratio": round(counts.get("Simulated", 0) / total, 4),
        }

    @classmethod
    def _risk_level(cls, topics: List[Dict[str, Any]]) -> str:
        max_risk = max((float((topic.get("driver_scores") or {}).get("risk") or 0) for topic in topics), default=0)
        if max_risk >= 0.66:
            return "high"
        if max_risk >= 0.36:
            return "medium"
        return "low"

    @classmethod
    def _layer_counts(cls, topics: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"Observed": 0, "Inferred": 0, "Simulated": 0}
        for topic in topics:
            layer = topic.get("source_layer") or "Inferred"
            counts[layer] = counts.get(layer, 0) + 1
        return counts

    @classmethod
    def _layers(cls, topics: List[Dict[str, Any]], opinion: Dict[str, Any], reaction: Dict[str, Any] | None) -> Dict[str, Any]:
        by_layer = {"Observed": [], "Inferred": [], "Simulated": []}
        for topic in topics:
            by_layer.setdefault(topic.get("source_layer") or "Inferred", []).append(topic)
        reaction = reaction or {}
        return {
            "observed": {
                "summary": cls._layer_summary(by_layer.get("Observed") or []),
                "topics": by_layer.get("Observed") or [],
                "reaction": reaction.get("fusion", {}).get("observed") if isinstance(reaction, dict) else None,
            },
            "inferred": {
                "summary": cls._layer_summary(by_layer.get("Inferred") or []),
                "topics": by_layer.get("Inferred") or [],
                "method": opinion.get("method") or [],
            },
            "simulated": {
                "summary": cls._layer_summary(by_layer.get("Simulated") or []),
                "topics": by_layer.get("Simulated") or [],
                "reaction": reaction.get("fusion", {}).get("simulated") if isinstance(reaction, dict) else None,
            },
        }

    @classmethod
    def _layer_summary(cls, topics: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "count": len(topics),
            "top_topic": topics[0].get("title") if topics else "",
            "avg_heat": round(sum(float(t.get("heat") or 0) for t in topics) / max(1, len(topics)), 2),
        }

    @classmethod
    def _pulses(cls, dashboard: Dict[str, Any], topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        topic_by_index = topics or []
        pulses = []
        for index, pulse in enumerate(dashboard.get("pulse_events") or []):
            topic = topic_by_index[index % len(topic_by_index)] if topic_by_index else {}
            topic_id = pulse.get("topic_id") or topic.get("id")
            if pulse.get("topic_id"):
                topic = next((item for item in topic_by_index if item.get("id") == pulse.get("topic_id")), topic)
            pulses.append({
                "id": pulse.get("id") or f"pulse_{index + 1}",
                "t": pulse.get("t"),
                "x": pulse.get("x", index + 1),
                "round": pulse.get("round"),
                "simulated_hour": pulse.get("simulated_hour"),
                "y": pulse.get("intensity", topic.get("heat", 0.5)),
                "volume": pulse.get("volume", 0),
                "layer": pulse.get("source_layer") or topic.get("source_layer", "Inferred"),
                "title": pulse.get("title"),
                "summary": pulse.get("summary"),
                "topic_id": topic_id,
                "source": (dashboard.get("source_status") or {}).get("source"),
                "model_scores": pulse.get("model_scores") or {},
            })
        return pulses

    @classmethod
    def _evidence(cls, topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        evidence = []
        for topic in topics:
            for index, text in enumerate(topic.get("evidence") or []):
                evidence.append({
                    "id": (topic.get("evidence_ids") or [f"{topic['id']}_ev_{index + 1}"])[0] if index == 0 else f"{topic['id']}_ev_{index + 1}",
                    "topic_id": topic.get("id"),
                    "source_layer": topic.get("source_layer"),
                    "text": text,
                })
        return evidence

    @classmethod
    def _model_status(cls, topics: List[Dict[str, Any]], dashboard: Dict[str, Any]) -> Dict[str, Any]:
        status = {}
        if topics:
            status.update(topics[0].get("model_status") or {})
        source_status = dashboard.get("source_status") or {}
        if source_status:
            status["dashboard"] = source_status
            if isinstance(source_status.get("model_status"), dict):
                status.update(source_status.get("model_status") or {})
        return status
