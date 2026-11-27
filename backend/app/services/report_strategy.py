"""Report-derived strategy, theme matching, and compliance helpers.

This module keeps the reusable pieces that used to live in the execution layer
without exposing the old execution product line or /api/execution routes.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ComplianceRule:
    rule_id: str
    name: str
    pattern: str
    action: str
    message: str


class ReportStrategyService:
    STORAGE_DIR = os.path.join(Config.UPLOAD_FOLDER, "report_strategy")
    STRATEGY_DIR = os.path.join(STORAGE_DIR, "strategies")

    PRODUCT_MAP: Dict[str, List[Dict[str, Any]]] = {
        "crypto": [
            {"code": "3066", "name": "Bitcoin Futures ETF", "tier": "flagship", "score": 0.92},
            {"code": "3068", "name": "Ether Futures ETF", "tier": "core", "score": 0.84},
            {"code": "9711", "name": "Coinbase 2x", "tier": "tactical", "score": 0.79},
        ],
        "macro_risk": [
            {"code": "3030", "name": "Gold ETF", "tier": "flagship", "score": 0.95},
            {"code": "3199", "name": "China Treasury ETF", "tier": "core", "score": 0.88},
            {"code": "3433", "name": "US Treasury 20Y+", "tier": "core", "score": 0.81},
        ],
        "us_tech": [
            {"code": "3034", "name": "Nasdaq 100 ETF", "tier": "flagship", "score": 0.93},
            {"code": "3454", "name": "US Magnificent Seven ETF", "tier": "core", "score": 0.89},
            {"code": "7266", "name": "Nasdaq 100 2x", "tier": "tactical", "score": 0.78},
        ],
        "china_policy": [
            {"code": "3101", "name": "CSI A500 ETF", "tier": "core", "score": 0.9},
            {"code": "3033", "name": "Hang Seng Tech ETF", "tier": "flagship", "score": 0.88},
            {"code": "82822", "name": "FTSE China A50 ETF", "tier": "flagship", "score": 0.86},
        ],
        "safe_haven": [
            {"code": "3030", "name": "Gold ETF", "tier": "flagship", "score": 0.94},
            {"code": "3469", "name": "High Dividend ETF", "tier": "core", "score": 0.85},
            {"code": "3433", "name": "US Treasury 20Y+", "tier": "core", "score": 0.82},
        ],
        "tech_growth": [
            {"code": "3033", "name": "Hang Seng Tech ETF", "tier": "flagship", "score": 0.94},
            {"code": "3454", "name": "US Magnificent Seven ETF", "tier": "core", "score": 0.9},
            {"code": "3109", "name": "STAR 50 ETF", "tier": "core", "score": 0.84},
        ],
    }

    COMPLIANCE_RULES: List[ComplianceRule] = [
        ComplianceRule("COMP-01", "收益承诺", r"稳赚|保本|保证涨|100%收益|稳赚不赔", "block", "禁止承诺或暗示确定性收益。"),
        ComplianceRule("COMP-02", "杠杆提示", r"2x|杠杆|反向", "warn", "杠杆或反向产品必须补充短线风险提示。"),
        ComplianceRule("COMP-03", "加密提示", r"比特币|以太币|crypto|BTC|ETH", "warn", "虚拟资产内容必须提示高波动与监管不确定性。"),
        ComplianceRule("COMP-04", "绝对化表达", r"唯一|最好|必然|一定|稳赚|稳赢", "block", "避免绝对化或确定性表达。"),
        ComplianceRule("COMP-05", "诱导互动", r"快买|马上买|现在上车|抄底|一夜暴富|暴涨", "block", "禁止诱导交易或夸大收益机会。"),
        ComplianceRule("COMP-06", "竞品贬低", r"不如我们|比.*差|吊打", "block", "不得贬低竞品。"),
    ]

    THEME_RULES: List[Dict[str, Any]] = [
        {
            "key": "crypto",
            "name": "加密货币热潮",
            "category": "行业轮动",
            "horizon": "short",
            "urgency": "high",
            "patterns": [r"比特币", r"以太", r"BTC", r"ETH", r"crypto", r"加密"],
            "products": PRODUCT_MAP["crypto"],
            "client_profiles": ["C05", "C04", "C03"],
            "compliance": ["COMP-01", "COMP-03"],
        },
        {
            "key": "macro_risk",
            "name": "宏观风险升温",
            "category": "宏观政策",
            "horizon": "mid",
            "urgency": "high",
            "patterns": [r"利率", r"议息", r"通胀", r"衰退", r"地缘", r"避险", r"黄金", r"债券"],
            "products": PRODUCT_MAP["macro_risk"],
            "client_profiles": ["C02", "C03", "C01"],
            "compliance": ["COMP-01"],
        },
        {
            "key": "us_tech",
            "name": "美股科技热度",
            "category": "区域热点",
            "horizon": "short",
            "urgency": "mid",
            "patterns": [r"美股", r"科技", r"AI", r"芯片", r"半导体", r"纳指", r"Nasdaq", r"MAG7"],
            "products": PRODUCT_MAP["us_tech"],
            "client_profiles": ["C04", "C03", "C02"],
            "compliance": ["COMP-01", "COMP-02"],
        },
        {
            "key": "china_policy",
            "name": "中国政策预期",
            "category": "宏观政策",
            "horizon": "mid",
            "urgency": "mid",
            "patterns": [r"中国", r"A股", r"港股", r"政策", r"刺激", r"消费", r"地产", r"恒生"],
            "products": PRODUCT_MAP["china_policy"],
            "client_profiles": ["C03", "C02", "C01"],
            "compliance": ["COMP-01"],
        },
        {
            "key": "safe_haven",
            "name": "避险资金流入",
            "category": "资金流向",
            "horizon": "short",
            "urgency": "mid",
            "patterns": [r"避险", r"资金流", r"净流入", r"波动", r"回撤", r"防御", r"高股息"],
            "products": PRODUCT_MAP["safe_haven"],
            "client_profiles": ["C02", "C01", "C03"],
            "compliance": ["COMP-01"],
        },
        {
            "key": "tech_growth",
            "name": "科技成长修复",
            "category": "行业轮动",
            "horizon": "short",
            "urgency": "low",
            "patterns": [r"成长", r"科技", r"创新", r"AI应用", r"互联网", r"云", r"芯片"],
            "products": PRODUCT_MAP["tech_growth"],
            "client_profiles": ["C03", "C04", "C02"],
            "compliance": ["COMP-01", "COMP-02"],
        },
    ]

    @classmethod
    def check_compliance(cls, text: str, platform: Optional[str] = None) -> Dict[str, Any]:
        status = "pass"
        issues: List[Dict[str, str]] = []
        normalized_text = text or ""

        for rule in cls.COMPLIANCE_RULES:
            if not re.search(rule.pattern, normalized_text, flags=re.IGNORECASE):
                continue

            issues.append(
                {
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "severity": "high" if rule.action == "block" else "medium",
                    "message": rule.message,
                    "action": rule.action,
                }
            )
            if rule.action == "block":
                status = "block"
            elif status != "block":
                status = "warn"

        return {"status": status, "issues": issues, "platform": platform}

    @classmethod
    def _split_markdown_sections(cls, markdown: str) -> List[Dict[str, str]]:
        sections: List[Dict[str, str]] = []
        current: Optional[Dict[str, str]] = None
        for line in (markdown or "").splitlines():
            heading = re.match(r"^#{1,3}\s+(.+)$", line.strip())
            if heading:
                if current:
                    sections.append(current)
                current = {"title": heading.group(1).strip(), "content": ""}
            elif current is not None:
                current["content"] += line + "\n"
        if current:
            sections.append(current)
        return sections

    @classmethod
    def _sections_from_report_dict(cls, report: Dict[str, Any]) -> List[Dict[str, str]]:
        outline = report.get("outline") or {}
        sections = outline.get("sections") or []
        normalized = [
            {
                "title": str(item.get("title") or f"Section {index + 1}"),
                "content": str(item.get("content") or item.get("description") or ""),
            }
            for index, item in enumerate(sections)
            if isinstance(item, dict)
        ]
        if normalized:
            return normalized
        markdown = report.get("markdown_content") or report.get("markdown") or ""
        return cls._split_markdown_sections(markdown)

    @classmethod
    def _report_title(cls, report: Dict[str, Any]) -> str:
        outline = report.get("outline") or {}
        return outline.get("title") or report.get("title") or report.get("report_id") or "Untitled report"

    @classmethod
    def _match_themes(cls, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []
        scored: List[Dict[str, Any]] = []
        for theme in cls.THEME_RULES:
            hits = 0
            for pattern in theme["patterns"]:
                hits += len(re.findall(pattern, text, flags=re.IGNORECASE))
            if hits:
                scored.append({"theme": theme, "hits": hits})
        scored.sort(key=lambda item: item["hits"], reverse=True)
        return scored

    @classmethod
    def _window_from_horizon(cls, horizon: str) -> str:
        if horizon == "short":
            return "1-2w"
        if horizon == "mid":
            return "1-3m"
        return "3m+"

    @classmethod
    def _build_signal_from_section(
        cls,
        report: Dict[str, Any],
        section: Dict[str, Any],
        theme: Dict[str, Any],
        hits: int,
        position: int,
    ) -> Dict[str, Any]:
        section_title = (section.get("title") or "").strip() or theme["name"]
        content = (section.get("content") or "").strip()
        snippets = [
            line.strip("-•·、 ").strip()
            for line in content.splitlines()
            if line.strip() and (line.strip().startswith(("-", "•", "·")) or len(line.strip()) <= 80)
        ]
        evidence = snippets[:3] if snippets else [content[:140]] if content else [section_title]
        confidence = max(0.55, min(0.95, 0.55 + 0.05 * hits))
        urgency = "high" if hits >= 4 else theme["urgency"]

        return {
            "id": f"RSIG-{str(report['report_id'])[:6].upper()}-{position:02d}",
            "name": theme["name"],
            "category": theme["category"],
            "strength": "high" if hits >= 4 else "mid" if hits >= 2 else "low",
            "confidence": round(confidence, 2),
            "horizon": theme["horizon"],
            "urgency": urgency,
            "trigger": {"z_score": round(1.0 + 0.4 * hits, 2), "source": f"report:{report['report_id']}"},
            "evidence": evidence,
            "headline": f"{report['title']} - {section_title}",
            "report_id": report["report_id"],
            "simulation_id": report.get("simulation_id"),
            "section_title": section_title,
            "theme_key": theme["key"],
            "created_at": report.get("created_at", _now_iso()),
        }

    @classmethod
    def _build_script(cls, signal: Dict[str, Any], product: Dict[str, Any], profile: str) -> str:
        return (
            f"{signal['name']} 信号正在升温。针对 {profile} 客户，可先用 {product['name']} 切入，"
            "同时明确说明风险边界、波动来源与适当性要求。"
        )

    @classmethod
    def _real_signal_to_brief(cls, signal: Dict[str, Any]) -> Dict[str, Any]:
        theme = next((item for item in cls.THEME_RULES if item["key"] == signal.get("theme_key")), None)
        products = (theme or {}).get("products") or [{"code": "0000", "name": "待定产品", "score": 0.6}]
        profiles = (theme or {}).get("client_profiles") or ["C03", "C02", "C01"]
        compliance = (theme or {}).get("compliance") or ["COMP-01"]
        actions = []
        for index, profile in enumerate(profiles[:3], start=1):
            product = products[min(index - 1, len(products) - 1)]
            actions.append(
                {
                    "priority": index,
                    "client_profile": profile,
                    "product": product.get("code"),
                    "product_name": product.get("name"),
                    "score": round(max(0.55, float(product.get("score", 0.7)) - (index - 1) * 0.05), 2),
                    "script": cls._build_script(signal, product, profile),
                }
            )

        return {
            "card_id": f"BRC-{uuid.uuid4().hex[:8].upper()}",
            "signal_id": signal["id"],
            "urgency": signal["urgency"],
            "window": cls._window_from_horizon(signal["horizon"]),
            "headline": signal["headline"],
            "summary": f"基于报告章节“{signal.get('section_title', '')}”，建议优先围绕 {actions[0]['product_name']} 做客户沟通准备。",
            "signals": [signal["id"]],
            "actions": actions,
            "compliance": compliance,
            "status": "new",
            "trace_id": f"trace_{uuid.uuid4().hex[:10]}",
            "created_at": signal.get("created_at", _now_iso()),
            "report_id": signal.get("report_id"),
            "simulation_id": signal.get("simulation_id"),
        }

    @classmethod
    def _signals_from_report_dict(cls, report: Dict[str, Any], max_signals: int = 6) -> List[Dict[str, Any]]:
        report_id = report.get("report_id") or "report_unknown"
        report_ref = {
            "report_id": report_id,
            "title": cls._report_title(report),
            "simulation_id": report.get("simulation_id"),
            "created_at": report.get("created_at") or _now_iso(),
        }
        sections = cls._sections_from_report_dict(report)
        signals: List[Dict[str, Any]] = []
        seen_keys = set()
        position = 0

        for section in sections:
            text = " ".join([section.get("title", ""), section.get("content", "")])
            matches = cls._match_themes(text)
            if not matches:
                continue
            top = matches[0]
            key = (top["theme"]["key"], section.get("title", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            position += 1
            signals.append(cls._build_signal_from_section(report_ref, section, top["theme"], top["hits"], position))
            if len(signals) >= max_signals:
                break

        if signals:
            return signals

        fallback_text = " ".join([
            cls._report_title(report),
            report.get("simulation_requirement") or "",
            (report.get("markdown_content") or "")[:5000],
        ])
        matches = cls._match_themes(fallback_text)
        if matches:
            top = matches[0]
            return [
                cls._build_signal_from_section(
                    report_ref,
                    {"title": cls._report_title(report), "content": fallback_text[:1000]},
                    top["theme"],
                    top["hits"],
                    1,
                )
            ]

        seed = deepcopy(
            {
                "id": f"RSIG-{report_id[:6].upper()}-00",
                "name": "报告核心议题",
                "category": "report",
                "strength": "mid",
                "confidence": 0.6,
                "horizon": "short",
                "urgency": "mid",
                "trigger": {"z_score": 1.2, "source": f"report:{report_id}"},
                "evidence": [cls._report_title(report)],
                "headline": cls._report_title(report),
                "report_id": report_id,
                "simulation_id": report.get("simulation_id"),
                "section_title": cls._report_title(report),
                "theme_key": "report_core",
                "created_at": report.get("created_at") or _now_iso(),
            }
        )
        return [seed]

    @classmethod
    def _strategy_markdown(cls, title: str, signals: List[Dict[str, Any]], briefs: List[Dict[str, Any]]) -> str:
        lines = [f"# CSOP Product Strategy - {title}", ""]
        for signal, brief in zip(signals, briefs):
            lines.append(f"## {signal.get('name', signal.get('id'))}")
            lines.append(f"- Signal: {signal.get('headline')}")
            lines.append(f"- Urgency: {brief.get('urgency')} / Window: {brief.get('window')}")
            for action in brief.get("actions", [])[:3]:
                lines.append(
                    f"- {action.get('client_profile')}: {action.get('product_name')} "
                    f"({action.get('product')}) score={action.get('score')}"
                )
            lines.append("")
        return "\n".join(lines).strip()

    @classmethod
    def _ensure_strategy_dir(cls) -> None:
        os.makedirs(cls.STRATEGY_DIR, exist_ok=True)

    @classmethod
    def _strategy_path(cls, report_id: str) -> str:
        return os.path.join(cls.STRATEGY_DIR, f"{report_id}.json")

    @classmethod
    def get_report_strategy(cls, report_id: str) -> Optional[Dict[str, Any]]:
        path = cls._strategy_path(report_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def save_report_strategy(cls, report_id: str, strategy: Dict[str, Any]) -> None:
        cls._ensure_strategy_dir()
        with open(cls._strategy_path(report_id), "w", encoding="utf-8") as f:
            json.dump(strategy, f, ensure_ascii=False, indent=2)

    @classmethod
    def build_strategy_for_report(cls, report: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        if hasattr(report, "to_dict"):
            report = report.to_dict()
        report_id = report.get("report_id")
        if not report_id:
            raise ValueError("report_id is required")
        if not force:
            existing = cls.get_report_strategy(report_id)
            if existing:
                return existing

        title = cls._report_title(report)
        signals = cls._signals_from_report_dict(report)
        briefs = [cls._real_signal_to_brief(signal) for signal in signals[:5]]
        product_matches: List[Dict[str, Any]] = []
        rule_suggestions: List[Dict[str, Any]] = []

        for signal, brief in zip(signals, briefs):
            for action in brief.get("actions", []):
                product_matches.append({
                    "signal_id": signal.get("id"),
                    "signal_name": signal.get("name"),
                    "theme_key": signal.get("theme_key"),
                    "client_profile": action.get("client_profile"),
                    "product": action.get("product"),
                    "product_name": action.get("product_name"),
                    "score": action.get("score"),
                    "script": action.get("script"),
                    "compliance": brief.get("compliance", []),
                })
            rule_suggestions.append({
                "signal_id": signal.get("id"),
                "rule": "map_signal_to_product",
                "rationale": brief.get("summary"),
                "compliance": brief.get("compliance", []),
            })

        strategy = {
            "strategy_id": f"strategy_{uuid.uuid4().hex[:12]}",
            "report_id": report_id,
            "simulation_id": report.get("simulation_id"),
            "generated_at": _now_iso(),
            "source": "report_strategy_service",
            "signals": signals,
            "briefs": briefs,
            "product_matches": product_matches,
            "rule_suggestions": rule_suggestions,
            "strategy_markdown": cls._strategy_markdown(title, signals, briefs),
            "sales_brief": "\n".join(brief.get("summary", "") for brief in briefs if brief.get("summary")),
            "training_outline": [
                {
                    "signal_id": signal.get("id"),
                    "scenario": signal.get("headline"),
                    "expected_action": (brief.get("actions") or [{}])[0].get("script", ""),
                }
                for signal, brief in zip(signals, briefs)
            ],
        }
        cls.save_report_strategy(report_id, strategy)
        return strategy
