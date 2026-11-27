"""Content Studio draft generation and compliance checks."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from .public_opinion_service import PublicOpinionService
from .report_agent import ReportManager
from .report_strategy import ReportStrategyService


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class ContentStudioService:
    STORAGE_DIR = os.path.join(Config.UPLOAD_FOLDER, "content_studio")
    PLATFORMS = ("xiaohongshu", "linkedin", "x", "wechat")

    @classmethod
    def get_studio(cls, report_id: str) -> Dict[str, Any]:
        saved = cls._load(report_id)
        if saved:
            return saved
        return cls.generate(report_id, save=True)

    @classmethod
    def generate(cls, report_id: str, options: Optional[Dict[str, Any]] = None, save: bool = True) -> Dict[str, Any]:
        report = ReportManager.get_report(report_id)
        if not report:
            raise ValueError(f"report {report_id} not found")

        opinion = PublicOpinionService.get_public_opinion(report_id)
        topics = opinion.get("topics") or []
        evidence_ids = [item.get("id") for item in opinion.get("evidence") or [] if item.get("id")]
        report_dict = report.to_dict()
        title = (report_dict.get("outline") or {}).get("title") or report_id
        summary = (opinion.get("summary") or {}).get("text") or (report_dict.get("outline") or {}).get("summary") or ""
        top_topic = topics[0] if topics else {"title": title, "summary": summary, "keywords": []}

        payload = {
            "report_id": report_id,
            "generated_at": _now_iso(),
            "platforms": {
                "xiaohongshu": [cls._draft_xiaohongshu(report_id, top_topic, summary)],
                "linkedin": [cls._draft_linkedin(report_id, top_topic, summary)],
                "x": [cls._draft_x(report_id, top_topic, summary)],
                "wechat": [cls._draft_wechat(report_id, top_topic, summary)],
            },
            "compliance": {},
            "source_basis": {
                "opinion_topics": [topic.get("id") for topic in topics[:5]],
                "report_sections": [section.get("title") for section in ReportStrategyService._sections_from_report_dict(report_dict)[:5]],
                "evidence_ids": evidence_ids[:12],
            },
        }

        for platform, posts in payload["platforms"].items():
            payload["compliance"][platform] = [cls.check(post.get("body", ""), platform, post).get("compliance") for post in posts]
            for post in posts:
                check = cls.check(post.get("body", ""), platform, post)["compliance"]
                post["compliance_status"] = check["status"]
                post["issues"] = check["issues"]
                post["publish_ready"] = check["status"] == "pass"

        if save:
            cls._save(report_id, payload)
        return payload

    @classmethod
    def check(cls, text: str, platform: Optional[str] = None, post: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        compliance = ReportStrategyService.check_compliance(text, platform=platform)
        issues = list(compliance.get("issues") or [])
        status = compliance.get("status", "pass")
        post = post or {}

        def add_issue(rule_id: str, message: str, severity: str = "medium") -> None:
            nonlocal status
            issues.append({"rule_id": rule_id, "name": "platform_rule", "severity": severity, "message": message, "action": "warn"})
            if status == "pass":
                status = "warn"

        if platform == "xiaohongshu":
            if len(post.get("title", "")) > 20:
                add_issue("XHS-01", "小红书标题建议不超过 20 字。")
            if len(text or "") > 1000:
                add_issue("XHS-02", "小红书正文建议不超过 1000 字。")
            if len(post.get("tags") or []) > 10:
                add_issue("XHS-03", "小红书标签建议不超过 10 个。")
        if platform == "x" and len(text or "") > 560:
            add_issue("X-01", "X 草稿超过短帖长度，建议拆成 thread。")

        compliance.update({"status": status, "issues": issues})
        return {"success": True, "compliance": compliance}

    @classmethod
    def patch_post(cls, post_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        for report_id, studio in cls._iter_saved():
            for platform, posts in (studio.get("platforms") or {}).items():
                for post in posts:
                    if post.get("post_id") != post_id:
                        continue
                    for key in ("title", "body", "tags", "status", "notes"):
                        if key in payload:
                            post[key] = payload[key]
                    post["updated_at"] = _now_iso()
                    check = cls.check(post.get("body", ""), platform, post)["compliance"]
                    post["compliance_status"] = check["status"]
                    post["issues"] = check["issues"]
                    post["publish_ready"] = check["status"] == "pass"
                    cls._save(report_id, studio)
                    return post
        raise ValueError(f"post {post_id} not found")

    @classmethod
    def _draft_xiaohongshu(cls, report_id: str, topic: Dict[str, Any], summary: str) -> Dict[str, Any]:
        title = cls._trim(topic.get("title") or "舆情变化", 20)
        body = "\n".join([
            f"今天关注：{topic.get('title') or '市场舆情变化'}",
            topic.get("summary") or summary,
            "观察点：声量是否继续扩散、反方观点是否增加、推演层结论是否被误读。",
            "风险提示：以上为仿真与舆情分析，不构成投资建议。",
        ])
        return cls._post(report_id, "xiaohongshu", title, body, ["舆情", "市场观察", "风险提示"])

    @classmethod
    def _draft_linkedin(cls, report_id: str, topic: Dict[str, Any], summary: str) -> Dict[str, Any]:
        title = f"Public opinion pulse: {topic.get('title') or 'market narrative'}"
        body = "\n\n".join([
            f"A new public-opinion pulse is forming around {topic.get('title') or 'the report theme'}.",
            topic.get("summary") or summary,
            "What matters next: separate observed evidence, inferred drivers, and simulated outcomes before turning the insight into client communication.",
            "This is a research note, not investment advice.",
        ])
        return cls._post(report_id, "linkedin", title, body, ["PublicOpinion", "MarketIntelligence", "Risk"])

    @classmethod
    def _draft_x(cls, report_id: str, topic: Dict[str, Any], summary: str) -> Dict[str, Any]:
        body = (
            f"{topic.get('title') or 'Market pulse'}: {topic.get('summary') or summary} "
            "Watch whether observed volume turns into stance conflict. Research only, not investment advice."
        )
        return cls._post(report_id, "x", cls._trim(topic.get("title") or "Market pulse", 64), cls._trim(body, 540), ["FinRex", "Opinion"])

    @classmethod
    def _draft_wechat(cls, report_id: str, topic: Dict[str, Any], summary: str) -> Dict[str, Any]:
        title = f"{topic.get('title') or '舆情主题'}：从声量到立场的三层观察"
        body = "\n\n".join([
            "一、发生了什么",
            topic.get("summary") or summary,
            "二、如何拆解",
            "Observed 层看真实输入与声量，Inferred 层看动因和分歧，Simulated 层看未来 24-72 小时可能演化。",
            "三、发布前检查",
            "避免确定性收益表述，保留证据链，并把仿真结论与现实观测清晰分开。",
        ])
        return cls._post(report_id, "wechat", title, body, ["舆情分析", "仿真报告", "内容准备"])

    @classmethod
    def _post(cls, report_id: str, platform: str, title: str, body: str, tags: List[str]) -> Dict[str, Any]:
        return {
            "post_id": f"cs_{platform}_{uuid.uuid4().hex[:10]}",
            "report_id": report_id,
            "platform": platform,
            "title": title,
            "body": body,
            "tags": tags,
            "status": "draft",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        text = text or ""
        return text[:limit]

    @classmethod
    def _ensure_dir(cls) -> None:
        os.makedirs(cls.STORAGE_DIR, exist_ok=True)

    @classmethod
    def _path(cls, report_id: str) -> str:
        return os.path.join(cls.STORAGE_DIR, f"{report_id}.json")

    @classmethod
    def _load(cls, report_id: str) -> Optional[Dict[str, Any]]:
        path = cls._path(report_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def _save(cls, report_id: str, payload: Dict[str, Any]) -> None:
        cls._ensure_dir()
        with open(cls._path(report_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @classmethod
    def _iter_saved(cls):
        cls._ensure_dir()
        for filename in os.listdir(cls.STORAGE_DIR):
            if not filename.endswith(".json"):
                continue
            report_id = filename[:-5]
            yield report_id, cls._load(report_id)

