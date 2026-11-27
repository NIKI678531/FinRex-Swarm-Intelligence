"""Build v2 public-opinion dashboard data from generated legacy reports.

The v2 report screen keeps the original three-layer shape, but the data here is
derived from a saved Step 4 report instead of the old demo bundle. The adapter is
inspired by the BettaFish deep-search flow: plan around report sections, extract
multi-source/commentary signals, reflect them into stakeholder viewpoints, then
project future hot topics and post drafts.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .report_strategy import ReportStrategyService
from .reaction.run_manager import ReactionRunManager
from .time_pulse_model import TimePulseModel

if TYPE_CHECKING:
    from .report_agent import Report


OBSERVED_TERMS = ["Observed", "观察", "现状", "事实", "数据", "新闻", "评论", "舆情", "声量", "传播", "热议"]
INFERRED_TERMS = ["Inferred", "推断", "研判", "原因", "动因", "归因", "影响", "分歧", "观点", "脉络"]
SIMULATED_TERMS = ["Simulated", "推演", "预测", "未来", "走势", "方向", "可能", "预计", "演化", "72h", "T+"]

ENGAGEMENT_TERMS = ["热议", "讨论", "转发", "评论", "关注", "舆情", "发酵", "传播", "热度", "帖子", "媒体", "社交", "声量", "KOL", "大V"]
RISK_TERMS = ["风险", "下行", "争议", "质疑", "不确定", "监管", "冲击", "负面", "恐慌", "暴跌", "回撤", "赎回", "合规", "危机"]
OPPORTUNITY_TERMS = ["机会", "利好", "增长", "配置", "看多", "正面", "回流", "上行", "修复", "反弹", "支持", "买入", "申购"]
FUTURE_TERMS = ["未来", "预测", "推演", "可能", "将", "预计", "趋势", "方向", "下一步", "短期", "长期", "72小时", "72h"]

STAKEHOLDER_RULES: List[Dict[str, Any]] = [
    {
        "id": "media_kol",
        "name": "媒体/KOL 放大者",
        "keywords": ["媒体", "KOL", "大V", "传播", "报道", "转发", "热搜", "新闻", "渠道"],
        "stance": "neutral",
        "profession": "信息扩散节点",
        "tags": ["media", "amplifier"],
    },
    {
        "id": "active_commenters",
        "name": "高活跃评论者",
        "keywords": ["评论", "跟帖", "讨论", "社区", "雪球", "微博", "论坛", "reddit", "散户", "投资者"],
        "stance": "neutral",
        "profession": "评论区意见样本",
        "tags": ["comment", "observed"],
    },
    {
        "id": "risk_sensitive",
        "name": "风险敏感用户",
        "keywords": ["风险", "担心", "质疑", "负面", "争议", "下跌", "监管", "不确定", "回撤"],
        "stance": "bear",
        "profession": "风险提示与反方观点",
        "tags": ["risk", "skeptic"],
    },
    {
        "id": "opportunity_followers",
        "name": "机会跟随者",
        "keywords": ["机会", "看多", "利好", "增长", "回流", "反弹", "配置", "申购", "支持"],
        "stance": "bull",
        "profession": "顺势参与与配置需求",
        "tags": ["opportunity", "momentum"],
    },
    {
        "id": "institutions",
        "name": "机构/专业投资者",
        "keywords": ["机构", "基金", "资管", "投顾", "卖方", "买方", "ETF", "产品", "组合", "配置"],
        "stance": "neutral",
        "profession": "专业配置与产品筛选",
        "tags": ["institution", "product"],
    },
    {
        "id": "regulators_compliance",
        "name": "监管/合规关注方",
        "keywords": ["监管", "合规", "政策", "披露", "适当性", "风险提示", "审查"],
        "stance": "bear",
        "profession": "监管与合规约束",
        "tags": ["compliance", "policy"],
    },
    {
        "id": "csop_product_side",
        "name": "CSOP 产品与客户侧",
        "keywords": ["CSOP", "南方东英", "客户", "销售", "产品", "ETF", "策略", "话术"],
        "stance": "neutral",
        "profession": "产品策略与客户沟通",
        "tags": ["csop", "strategy"],
    },
]

ANGLE_CATALOG = [
    {"angle": "news", "label": "新闻解读", "tone": "brand"},
    {"angle": "commentary", "label": "评论区脉络", "tone": "neutral"},
    {"angle": "risk", "label": "风险反方", "tone": "bear"},
]


def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now().replace(microsecond=0)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now().replace(microsecond=0)


def _trim(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _count_terms(text: str, terms: List[str]) -> int:
    if not text:
        return 0
    return sum(len(re.findall(re.escape(term), text, flags=re.IGNORECASE)) for term in terms)


def _split_sentences(text: str, limit: int = 8) -> List[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s+|\n+|[•●·]", text or "")
    sentences = [_trim(part, 220) for part in parts if _trim(part, 220)]
    return sentences[:limit]


def _line_band(points: int, base: float, amplitude: float) -> Dict[str, List[Any]]:
    x, mean, low, high = [], [], [], []
    for i in range(points):
        wave = ((i % 6) / 5) - 0.35
        value = max(0.01, base + amplitude * wave)
        x.append(f"+{i * 3}h")
        mean.append(round(value, 2))
        low.append(round(max(0.0, value * 0.74), 2))
        high.append(round(value * 1.26, 2))
    return {"x": x, "mean": mean, "low": low, "high": high}


def _safe_id(value: str, fallback: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_\-]+", "_", value or "").strip("_")
    return raw[:48] or fallback


def _sentence_stem(text: str, limit: int = 260) -> str:
    return re.sub(r"[。.!！?？]+$", "", _trim(text, limit)).strip()


class ReportV2Adapter:
    @classmethod
    def build(cls, report: "Report") -> Dict[str, Any]:
        report_dict = report.to_dict()
        sections = ReportStrategyService._sections_from_report_dict(report_dict)
        if not sections:
            sections = cls._fallback_sections(report_dict)

        reaction_run = cls._find_reaction_run(report_dict)
        strategy = ReportStrategyService.build_strategy_for_report(report_dict)
        opinion = cls._build_public_opinion_model(report_dict, sections, reaction_run, strategy)

        # 同 simulation 下的金融强预测报告（若存在）
        financial_block: Optional[Dict[str, Any]] = None
        try:
            from .report_agent import ReportManager  # local import to avoid cycle
            sim_id = report_dict.get("simulation_id")
            if sim_id and report_dict.get("report_type") != "financial":
                fin_report = ReportManager.get_report_by_simulation(sim_id, "financial")
                if fin_report:
                    fin_dict = fin_report.to_dict()
                    financial_block = {
                        "report_id": fin_dict.get("report_id"),
                        "status": fin_dict.get("status"),
                        "outline": fin_dict.get("outline"),
                        "markdown_content": fin_dict.get("markdown_content"),
                        "financial_context": fin_dict.get("financial_context"),
                    }
            elif report_dict.get("report_type") == "financial":
                financial_block = {
                    "report_id": report_dict.get("report_id"),
                    "status": report_dict.get("status"),
                    "outline": report_dict.get("outline"),
                    "markdown_content": report_dict.get("markdown_content"),
                    "financial_context": report_dict.get("financial_context"),
                }
        except Exception:
            financial_block = None

        predictions = cls._build_predictions(strategy, sections, opinion)
        if financial_block is not None:
            predictions = {**predictions, "financial": financial_block}

        return {
            "meta": cls._build_meta(report_dict, sections, opinion),
            "dashboard": cls._build_dashboard(report_dict, sections, reaction_run, opinion),
            "personas": cls._build_personas(reaction_run, strategy, opinion),
            "predictions": predictions,
            "posts_by_theme": cls._build_posts_by_theme(strategy, opinion),
            "strategy": strategy,
            "public_opinion": opinion,
            "reaction": reaction_run.to_dict() if reaction_run else None,
            "financial": financial_block,
        }

    @classmethod
    def _fallback_sections(cls, report: Dict[str, Any]) -> List[Dict[str, str]]:
        outline = report.get("outline") or {}
        body = report.get("markdown_content") or outline.get("summary") or report.get("simulation_requirement") or ""
        return [{"title": outline.get("title") or "报告核心内容", "content": body}]

    @classmethod
    def _build_meta(cls, report: Dict[str, Any], sections: List[Dict[str, str]], opinion: Dict[str, Any]) -> Dict[str, Any]:
        outline = report.get("outline") or {}
        summary = outline.get("summary") or opinion.get("summary") or _trim(report.get("markdown_content", ""), 360)
        return {
            "id": report.get("report_id"),
            "simulation_id": report.get("simulation_id"),
            "status": report.get("status"),
            "generated_at": report.get("completed_at") or report.get("created_at"),
            "summary": summary,
            "sections": [
                {"id": "dashboard", "kind": "dashboard", "status": "ready"},
                {"id": "personas", "kind": "personas", "status": "ready"},
                {"id": "predictions", "kind": "predictions", "status": "ready"},
            ],
            "source_sections": [
                {"title": s.get("title"), "size": len(s.get("content", ""))}
                for s in sections
            ],
            "analysis_basis": {
                "source": "legacy_report",
                "method": "section_signal_extraction_and_public_opinion_projection",
                "hot_topics": len(opinion.get("hot_topics") or []),
                "stakeholders": len(opinion.get("stakeholders") or []),
            },
        }

    @classmethod
    def _find_reaction_run(cls, report: Dict[str, Any]):
        blob = "\n".join([
            report.get("simulation_requirement") or "",
            report.get("markdown_content") or "",
        ])
        match = re.search(r"react_[A-Za-z0-9]+", blob)
        if not match:
            return None
        return ReactionRunManager.get_run(match.group(0))

    @classmethod
    def _sentiment_score(cls, reaction_run) -> float:
        if not reaction_run or not reaction_run.fusion:
            return 0.0
        fusion = reaction_run.fusion
        inferred = fusion.inferred or {}
        observed = fusion.observed or {}
        dist = inferred.get("adjusted_sentiment_distribution") or observed.get("sentiment_distribution") or {}
        return round(float(dist.get("positive", 0.0)) - float(dist.get("negative", 0.0)), 2)

    @classmethod
    def _build_public_opinion_model(
        cls,
        report: Dict[str, Any],
        sections: List[Dict[str, str]],
        reaction_run,
        strategy: Dict[str, Any],
    ) -> Dict[str, Any]:
        section_signals = [cls._analyze_section(section, index, strategy) for index, section in enumerate(sections, start=1)]
        hot_topics = sorted(section_signals, key=lambda item: item["heat"], reverse=True)[:6]

        if len(hot_topics) < 3:
            hot_topics = cls._extend_topics_from_strategy(hot_topics, strategy)

        # 给每个 hot_topic 增加预测字段（predicted_intensity / horizon / related_products）
        cls._enrich_topics_with_prediction(hot_topics, strategy)

        # 派生热点金融产品（基于 strategy.product_matches + section text 频次）
        hot_products = cls._derive_hot_products(strategy, sections, hot_topics)

        stakeholders = cls._extract_stakeholders(report, sections, hot_topics, reaction_run)
        viewpoint_map = cls._build_viewpoint_map(stakeholders, hot_topics)

        summary = cls._public_opinion_summary(report, hot_topics, stakeholders)
        return {
            "summary": summary,
            "method": [
                "section_planning",
                "observed_inferred_simulated_classification",
                "stakeholder_viewpoint_extraction",
                "future_heat_projection",
                "product_heat_projection",
                "post_report_generation",
            ],
            "hot_topics": hot_topics,
            "hot_products": hot_products,
            "section_signals": section_signals,
            "stakeholders": stakeholders,
            "viewpoint_map": viewpoint_map,
        }

    @classmethod
    def _analyze_section(cls, section: Dict[str, str], index: int, strategy: Dict[str, Any]) -> Dict[str, Any]:
        title = _trim(section.get("title") or f"主题 {index}", 80)
        content = section.get("content") or ""
        text = f"{title}\n{content}"
        length_score = min(0.28, len(content) / 7200)
        engagement = _count_terms(text, ENGAGEMENT_TERMS)
        risk = _count_terms(text, RISK_TERMS)
        opportunity = _count_terms(text, OPPORTUNITY_TERMS)
        future = _count_terms(text, FUTURE_TERMS)
        layer = cls._classify_layer(text)
        strategy_hits = cls._strategy_hits(text, strategy)
        heat = 0.34 + length_score + min(0.18, engagement * 0.025) + min(0.16, risk * 0.022) + min(0.12, future * 0.024) + min(0.1, strategy_hits * 0.018)
        heat = round(max(0.36, min(0.96, heat)), 2)
        confidence = round(max(0.48, min(0.92, 0.46 + length_score + min(0.2, (engagement + future + strategy_hits) * 0.018))), 2)
        stance = cls._stance_from_counts(opportunity, risk)
        sentences = _split_sentences(content, limit=10)
        evidence = cls._pick_evidence(sentences, ENGAGEMENT_TERMS + RISK_TERMS + FUTURE_TERMS)
        keywords = cls._extract_keywords(text, strategy)

        return {
            "id": f"theme_{index}_{_safe_id(title, 'topic')}",
            "section_index": index,
            "source_layer": layer,
            "title": title,
            "summary": evidence[0] if evidence else _trim(content, 180) or title,
            "heat": heat,
            "confidence": confidence,
            "stance": stance,
            "driver_scores": {
                "engagement": min(1.0, round(engagement / 6, 2)),
                "risk": min(1.0, round(risk / 6, 2)),
                "opportunity": min(1.0, round(opportunity / 6, 2)),
                "future": min(1.0, round(future / 5, 2)),
                "evidence": min(1.0, round(len(sentences) / 8, 2)),
            },
            "keywords": keywords[:8],
            "evidence": evidence[:4],
            "evidence_ids": [f"sec_{index:02d}"],
            "post_seed": cls._post_seed_from_section(title, evidence, content),
        }

    @classmethod
    def _classify_layer(cls, text: str) -> str:
        scores = {
            "Observed": _count_terms(text, OBSERVED_TERMS),
            "Inferred": _count_terms(text, INFERRED_TERMS),
            "Simulated": _count_terms(text, SIMULATED_TERMS),
        }
        return max(scores, key=scores.get) if max(scores.values()) else "Inferred"

    @classmethod
    def _strategy_hits(cls, text: str, strategy: Dict[str, Any]) -> int:
        hits = 0
        for signal in strategy.get("signals") or []:
            hits += _count_terms(text, [signal.get("name") or "", signal.get("headline") or "", signal.get("theme_key") or ""])
        for rule in getattr(ReportStrategyService, "THEME_RULES", []):
            terms = [re.sub(r"\\b", "", item) for item in rule.get("patterns", [])]
            hits += _count_terms(text, [term for term in terms if term])
        return hits

    @classmethod
    def _stance_from_counts(cls, opportunity: int, risk: int) -> str:
        if opportunity >= risk + 2:
            return "bull"
        if risk >= opportunity + 2:
            return "bear"
        if risk >= 2 and opportunity >= 2:
            return "contrarian"
        return "neutral"

    @classmethod
    def _pick_evidence(cls, sentences: List[str], terms: List[str]) -> List[str]:
        scored = []
        for sentence in sentences:
            score = _count_terms(sentence, terms) + min(3, len(sentence) // 60)
            scored.append((score, sentence))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [sentence for score, sentence in scored if sentence][:4]

    @classmethod
    def _extract_keywords(cls, text: str, strategy: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for rule in getattr(ReportStrategyService, "THEME_RULES", []):
            for pattern in rule.get("patterns", []):
                term = re.sub(r"\\b", "", pattern)
                if term and re.search(re.escape(term), text, flags=re.IGNORECASE):
                    candidates.append(rule.get("name") or term)
        for signal in strategy.get("signals") or []:
            for key in ("name", "headline", "category"):
                value = signal.get(key)
                if value and value in text:
                    candidates.append(value)
        for term in ENGAGEMENT_TERMS + RISK_TERMS + OPPORTUNITY_TERMS + FUTURE_TERMS:
            if re.search(re.escape(term), text, flags=re.IGNORECASE):
                candidates.append(term)

        deduped = []
        for item in candidates:
            if item and item not in deduped:
                deduped.append(item)
        return deduped or ["报告主题", "舆情推演"]

    @classmethod
    def _post_seed_from_section(cls, title: str, evidence: List[str], content: str) -> str:
        if evidence:
            return evidence[0]
        return _trim(content, 220) or title

    @classmethod
    def _enrich_topics_with_prediction(cls, hot_topics: List[Dict[str, Any]], strategy: Dict[str, Any]) -> None:
        """给每个 hot_topic 增补预测字段（不破坏既有字段）。"""
        product_matches = strategy.get("product_matches") or []
        for topic in hot_topics:
            heat = float(topic.get("heat") or 0.5)
            future_score = float((topic.get("driver_scores") or {}).get("future") or 0.5)
            # 预测强度：综合 heat + future
            predicted_intensity = round(min(1.0, heat * 0.6 + future_score * 0.4), 2)
            # 预测时间窗口
            if predicted_intensity >= 0.7:
                horizon = "1-3 days"
            elif predicted_intensity >= 0.5:
                horizon = "1-2 weeks"
            else:
                horizon = "2-4 weeks"
            # 关联产品（与 keywords 模糊匹配）
            related_products: List[Dict[str, Any]] = []
            keywords = [str(k).lower() for k in (topic.get("keywords") or [])]
            for match in product_matches[:10]:
                prod_name = (match.get("product_name") or match.get("product") or "").lower()
                signal_name = (match.get("signal_name") or "").lower()
                if not prod_name and not signal_name:
                    continue
                hit = any(kw and (kw in prod_name or kw in signal_name) for kw in keywords)
                if hit or len(related_products) < 1:
                    related_products.append({
                        "product_name": match.get("product_name") or match.get("product") or "—",
                        "ticker": match.get("ticker") or match.get("symbol"),
                        "score": float(match.get("score") or 0.5),
                    })
                if len(related_products) >= 3:
                    break
            topic["predicted_intensity"] = predicted_intensity
            topic["horizon"] = horizon
            topic["related_products"] = related_products

    @classmethod
    def _derive_hot_products(
        cls,
        strategy: Dict[str, Any],
        sections: List[Dict[str, str]],
        hot_topics: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """从 strategy.product_matches + 报告章节文本派生热点金融产品。"""
        product_matches = strategy.get("product_matches") or []
        if not product_matches:
            return []

        # 拼接所有 section text 做频次统计
        full_text = " ".join((s.get("title", "") + " " + s.get("content", "")) for s in sections).lower()

        hot_products: List[Dict[str, Any]] = []
        for index, match in enumerate(product_matches[:8], start=1):
            product_name = match.get("product_name") or match.get("product") or f"Product {index}"
            ticker = match.get("ticker") or match.get("symbol") or ""
            base_score = float(match.get("score") or 0.5)

            # 频次统计：name + ticker 在报告全文中的出现次数
            mention_count = 0
            for token in [product_name.lower(), ticker.lower()] if ticker else [product_name.lower()]:
                if token and len(token) >= 2:
                    mention_count += full_text.count(token)

            # 关注度评分：策略 score（60%）+ 频次（40%，归一化）
            mention_norm = min(1.0, mention_count / 5.0)
            attention = round(base_score * 0.6 + mention_norm * 0.4, 2)

            # 关联话题
            related_topic_ids = []
            prod_lower = product_name.lower()
            for topic in hot_topics:
                kws = [str(k).lower() for k in (topic.get("keywords") or [])]
                if any(kw and kw in prod_lower for kw in kws) or any(kw and kw in (match.get("signal_name") or "").lower() for kw in kws):
                    related_topic_ids.append(topic["id"])
                if len(related_topic_ids) >= 3:
                    break

            hot_products.append({
                "id": f"product_{_safe_id(ticker or product_name, str(index))}",
                "product_name": product_name,
                "ticker": ticker or None,
                "category": match.get("category") or match.get("client_profile") or "—",
                "attention_score": attention,
                "predicted_intensity": attention,
                "mention_count": mention_count,
                "horizon": "1-2 weeks" if attention >= 0.5 else "2-4 weeks",
                "client_profile": match.get("client_profile"),
                "script": _trim(match.get("script") or "", 160),
                "related_topic_ids": related_topic_ids,
                "source_layer": "Simulated",
            })

        # 按 attention 降序
        hot_products.sort(key=lambda p: p["attention_score"], reverse=True)
        return hot_products[:6]

    @classmethod
    def _extend_topics_from_strategy(cls, hot_topics: List[Dict[str, Any]], strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        existing = {topic["id"] for topic in hot_topics}
        out = list(hot_topics)
        for index, signal in enumerate(strategy.get("signals") or [], start=1):
            theme_id = f"theme_strategy_{_safe_id(signal.get('theme_key') or signal.get('id') or str(index), str(index))}"
            if theme_id in existing:
                continue
            evidence = signal.get("evidence") or []
            out.append({
                "id": theme_id,
                "section_index": index,
                "source_layer": "Simulated",
                "title": signal.get("name") or signal.get("headline") or f"策略主题 {index}",
                "summary": _trim(" ".join(evidence), 180) or signal.get("headline") or "由报告信号映射出的舆情方向",
                "heat": round(float(signal.get("confidence") or 0.58), 2),
                "confidence": round(float(signal.get("confidence") or 0.58), 2),
                "stance": "neutral",
                "driver_scores": {"engagement": 0.45, "risk": 0.35, "opportunity": 0.45, "future": 0.65, "evidence": 0.5},
                "keywords": [signal.get("category") or "策略信号", signal.get("theme_key") or "舆情方向"],
                "evidence": evidence[:4],
                "evidence_ids": evidence[:4] or [signal.get("id") or theme_id],
                "post_seed": signal.get("headline") or _trim(" ".join(evidence), 220),
            })
            if len(out) >= 5:
                break
        return out

    @classmethod
    def _extract_stakeholders(
        cls,
        report: Dict[str, Any],
        sections: List[Dict[str, str]],
        hot_topics: List[Dict[str, Any]],
        reaction_run,
    ) -> List[Dict[str, Any]]:
        text = "\n".join([report.get("simulation_requirement") or "", report.get("markdown_content") or ""] + [
            f"{section.get('title', '')}\n{section.get('content', '')}" for section in sections
        ])
        scored: List[Dict[str, Any]] = []
        for rule in STAKEHOLDER_RULES:
            hits = _count_terms(text, rule["keywords"])
            related = cls._related_topics_for_rule(rule, hot_topics)
            if hits == 0 and not related:
                continue
            score = hits + len(related) * 2
            scored.append({
                "id": f"stakeholder_{rule['id']}",
                "name": rule["name"],
                "stance": rule["stance"],
                "profession": rule["profession"],
                "tags": rule["tags"],
                "hits": score,
                "related_topic_ids": [topic["id"] for topic in related[:3]],
                "viewpoint": cls._stakeholder_viewpoint(rule, related or hot_topics[:2]),
            })

        if reaction_run and reaction_run.fusion:
            for index, segment in enumerate((reaction_run.fusion.simulated or {}).get("segments") or [], start=1):
                scored.append({
                    "id": f"stakeholder_reaction_{index}",
                    "name": segment.get("segment") or f"评论区样本 {index}",
                    "stance": "neutral",
                    "profession": segment.get("basis") or "Observed/Inferred/Simulated fusion",
                    "tags": ["reaction", "observed" if reaction_run.comments_count else "simulated"],
                    "hits": max(1, int(float(segment.get("share") or 0.12) * 20)),
                    "related_topic_ids": [topic["id"] for topic in hot_topics[:2]],
                    "viewpoint": segment.get("likely_reaction") or segment.get("basis") or "评论区融合推演样本",
                })

        if not scored:
            scored = cls._default_stakeholders(hot_topics)

        total = sum(item["hits"] for item in scored) or len(scored) or 1
        scored.sort(key=lambda item: item["hits"], reverse=True)
        for item in scored:
            item["share"] = round(max(0.08, min(0.42, item["hits"] / total)), 2)
            item["influence"] = round(max(0.18, min(0.92, item["share"] + 0.28)), 2)
        return scored[:7]

    @classmethod
    def _related_topics_for_rule(cls, rule: Dict[str, Any], hot_topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        related = []
        for topic in hot_topics:
            blob = " ".join([topic.get("title", ""), topic.get("summary", ""), " ".join(topic.get("keywords") or [])])
            if _count_terms(blob, rule["keywords"]):
                related.append(topic)
        return related

    @classmethod
    def _stakeholder_viewpoint(cls, rule: Dict[str, Any], topics: List[Dict[str, Any]]) -> str:
        topic_text = "、".join(topic.get("title", "主题") for topic in topics[:2]) or "核心议题"
        if rule["stance"] == "bear":
            return f"围绕{topic_text}，主要强调风险边界、信息缺口和合规约束。"
        if rule["stance"] == "bull":
            return f"围绕{topic_text}，更关注机会窗口、趋势延续和可执行的参与路径。"
        return f"围绕{topic_text}，承担信息整合、观点转译和分歧放大的作用。"

    @classmethod
    def _default_stakeholders(cls, hot_topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seed = hot_topics[:2]
        defaults = [STAKEHOLDER_RULES[0], STAKEHOLDER_RULES[2], STAKEHOLDER_RULES[3]]
        return [
            {
                "id": f"stakeholder_{rule['id']}",
                "name": rule["name"],
                "stance": rule["stance"],
                "profession": rule["profession"],
                "tags": rule["tags"],
                "hits": 1,
                "related_topic_ids": [topic["id"] for topic in seed],
                "viewpoint": cls._stakeholder_viewpoint(rule, seed),
            }
            for rule in defaults
        ]

    @classmethod
    def _build_viewpoint_map(cls, stakeholders: List[Dict[str, Any]], hot_topics: List[Dict[str, Any]]) -> Dict[str, Any]:
        nodes = [{"id": topic["id"], "label": topic["title"], "type": "topic", "heat": topic["heat"]} for topic in hot_topics[:5]]
        edges = []
        for stakeholder in stakeholders:
            nodes.append({
                "id": stakeholder["id"],
                "label": stakeholder["name"],
                "type": "stakeholder",
                "stance": stakeholder["stance"],
                "influence": stakeholder.get("influence", 0.3),
            })
            related = stakeholder.get("related_topic_ids") or [topic["id"] for topic in hot_topics[:1]]
            for topic_id in related[:3]:
                edges.append({
                    "source": stakeholder["id"],
                    "target": topic_id,
                    "label": "关注/放大",
                    "weight": stakeholder.get("influence", 0.3),
                })
        return {"nodes": nodes, "edges": edges}

    @classmethod
    def _public_opinion_summary(cls, report: Dict[str, Any], hot_topics: List[Dict[str, Any]], stakeholders: List[Dict[str, Any]]) -> str:
        title = (report.get("outline") or {}).get("title") or report.get("report_id") or "报告"
        top_topic = hot_topics[0]["title"] if hot_topics else "核心议题"
        top_stakeholder = stakeholders[0]["name"] if stakeholders else "主要利益相关方"
        return f"基于《{title}》的二次舆情推演：当前最高热度来自“{top_topic}”，主要由{top_stakeholder}推动；后续看板按报告章节抽取事实层、研判层和推演层信号。"

    @classmethod
    def _build_dashboard(
        cls,
        report: Dict[str, Any],
        sections: List[Dict[str, str]],
        reaction_run,
        opinion: Dict[str, Any],
    ) -> Dict[str, Any]:
        topics = opinion.get("hot_topics") or []
        sentiment = cls._sentiment_score(reaction_run) or cls._sentiment_from_topics(topics)
        dynamic_dashboard = TimePulseModel.build_dashboard(
            report=report,
            topics=topics,
            fallback_sentiment=sentiment,
            fallback_active_personas=cls._active_persona_count(reaction_run, opinion),
        )
        if dynamic_dashboard:
            return dynamic_dashboard

        start = _parse_dt(report.get("created_at"))
        observed_count = reaction_run.comments_count if reaction_run else 0
        selected_count = reaction_run.selected_articles_count if reaction_run else 0
        base_volume = max(36, observed_count or selected_count * 12 or len(sections) * 72 or 80)

        timeline = []
        for i in range(24):
            topic = topics[i % len(topics)] if topics else {"heat": 0.48, "driver_scores": {}}
            pulse = 1.0 + (topic.get("heat", 0.48) * 0.9 if i in {4, 9, 14, 19} else topic.get("heat", 0.48) * 0.25)
            drift = 0.58 + (i % 5) * 0.07
            volume = int(base_volume * drift * pulse)
            timeline.append({
                "t": (start + timedelta(hours=i * 3)).isoformat(),
                "x": i * 3,
                "round": i,
                "simulated_hour": i * 3,
                "volume": volume,
                "sentiment": round(max(-1.0, min(1.0, sentiment + (i - 10) * 0.01)), 2),
                "emotion_intensity": 0.0,
                "risk_intensity": round(float((topic.get("driver_scores") or {}).get("risk") or 0), 2),
                "pulse_score": 0.0,
                "burst_state": "synthetic",
                "platform_breakdown": {},
                "active_personas": cls._active_persona_count(reaction_run, opinion),
            })

        pulse_events = []
        for index, topic in enumerate(topics[:4]):
            point = timeline[min(4 + index * 5, len(timeline) - 1)]
            pulse_events.append({
                "id": f"pulse_{report.get('report_id')}_{index + 1}",
                "t": point["t"],
                "x": point.get("x"),
                "round": point.get("round"),
                "simulated_hour": point.get("simulated_hour"),
                "volume": point["volume"],
                "intensity": topic.get("heat", 0.5),
                "title": topic.get("title") or f"舆情脉冲 {index + 1}",
                "summary": topic.get("summary") or "由报告章节二次分析生成的热点脉冲",
                "trigger_post_id": f"{report.get('report_id')}_{topic.get('id')}",
                "source_layer": topic.get("source_layer") or "Inferred",
                "trigger_action_ids": [],
                "topic_id": topic.get("id"),
                "model_scores": {"pulse_score": 0.0, "burst_state": "synthetic"},
            })

        key_events = [
            {
                "t": timeline[min((index + 1) * 3, len(timeline) - 1)]["t"],
                "label": topic.get("title") or f"报告热点 {index + 1}",
                "weight": topic.get("heat", 0.5),
                "post_ids": [f"{report.get('report_id')}_{topic.get('id')}"] + topic.get("evidence_ids", [])[:2],
                "pulse_id": f"pulse_{report.get('report_id')}_{index + 1}",
                "action_ids": [],
            }
            for index, topic in enumerate(topics[:6])
        ]

        return {
            "kpis": {
                "total_volume": sum(item["volume"] for item in timeline),
                "peak_time": max(timeline, key=lambda item: item["volume"])["t"],
                "sentiment_avg": sentiment,
                "active_personas": cls._active_persona_count(reaction_run, opinion),
            },
            "timeline": timeline,
            "pulse_events": pulse_events,
            "key_events": key_events,
            "source_status": {
                "source": "synthetic_fallback",
                "is_dynamic": False,
                "simulation_id": report.get("simulation_id"),
                "files_read": 0,
                "actions_count": 0,
                "round_event_count": 0,
                "bad_lines": 0,
                "fallback_reason": "missing_or_empty_oasis_action_stream",
                "model_pipeline": ["legacy_report_section_synthetic_dashboard"],
            },
        }

    @classmethod
    def _sentiment_from_topics(cls, topics: List[Dict[str, Any]]) -> float:
        if not topics:
            return 0.0
        score = 0.0
        for topic in topics:
            stance = topic.get("stance")
            if stance == "bull":
                score += topic.get("heat", 0.5) * 0.35
            elif stance == "bear":
                score -= topic.get("heat", 0.5) * 0.35
        return round(max(-1.0, min(1.0, score / max(1, len(topics)))), 2)

    @classmethod
    def _active_persona_count(cls, reaction_run, opinion: Dict[str, Any]) -> int:
        reaction_count = 0
        if reaction_run and reaction_run.fusion:
            reaction_count = max(len((reaction_run.fusion.simulated or {}).get("segments") or []), reaction_run.comments_count or 0)
        stakeholder_count = sum(max(1, int((item.get("share") or 0.1) * 100)) for item in opinion.get("stakeholders") or [])
        return max(reaction_count, stakeholder_count, len(opinion.get("stakeholders") or []) * 8)

    @classmethod
    def _build_personas(cls, reaction_run, strategy: Dict[str, Any], opinion: Dict[str, Any]) -> Dict[str, Any]:
        stakeholders = opinion.get("stakeholders") or []
        if not stakeholders:
            stakeholders = [
                {
                    "id": f"stakeholder_strategy_{index}",
                    "name": match.get("client_profile") or "CSOP 客户侧",
                    "share": max(0.1, float(match.get("score") or 0.5)),
                    "viewpoint": match.get("script") or match.get("product_name") or "CSOP product strategy audience",
                    "profession": match.get("signal_name") or "CSOP strategy",
                    "stance": "neutral",
                    "tags": ["csop", "strategy"],
                    "related_topic_ids": [],
                    "influence": max(0.2, float(match.get("score") or 0.5)),
                }
                for index, match in enumerate((strategy.get("product_matches") or [])[:5], start=1)
            ]

        clusters, personas = [], []
        for index, stakeholder in enumerate(stakeholders[:7], start=1):
            persona_id = f"persona_{_safe_id(stakeholder.get('id', str(index)), str(index))}"
            cluster_id = f"cluster_{_safe_id(stakeholder.get('id', str(index)), str(index))}"
            share = float(stakeholder.get("share") or 0.14)
            influence = float(stakeholder.get("influence") or share)
            clusters.append({
                "id": cluster_id,
                "name": stakeholder.get("name") or f"利益相关方 {index}",
                "size": max(1, int(round(share * 100))),
                "summary": stakeholder.get("viewpoint") or "报告派生的利益相关方观点簇",
                "top_persona_ids": [persona_id],
                "related_topic_ids": stakeholder.get("related_topic_ids") or [],
            })
            personas.append({
                "id": persona_id,
                "name": stakeholder.get("name") or f"利益相关方 {index}",
                "avatar_seed": persona_id,
                "cluster_id": cluster_id,
                "profession": stakeholder.get("profession") or "public opinion stakeholder",
                "tags": stakeholder.get("tags") or ["report-derived"],
                "dimensions": {
                    "demographics": {"age": "n/a", "gender": "n/a", "city": "n/a"},
                    "psychology": {"mbti": "n/a", "risk": cls._risk_label(stakeholder.get("stance")), "big5": "n/a"},
                    "investment": {"style": "event-driven", "horizon": "0-72h", "portfolio": "n/a"},
                    "behavior": {"post_freq": round(share * 10, 2), "reply_rate": round(min(0.95, share + 0.12), 2), "peak_hour": "n/a"},
                    "social": {"followers": int(influence * 1000), "influence": min(0.95, influence), "follows": []},
                    "signals": {"stance": stakeholder.get("stance") or "neutral", "momentum": cls._momentum_label(influence), "last_active": ""},
                },
            })
        return {"clusters": clusters, "personas": personas, "viewpoint_map": opinion.get("viewpoint_map") or {}}

    @classmethod
    def _risk_label(cls, stance: Optional[str]) -> str:
        if stance == "bear":
            return "high"
        if stance == "bull":
            return "medium"
        return "medium-low"

    @classmethod
    def _momentum_label(cls, influence: float) -> str:
        if influence >= 0.65:
            return "strong"
        if influence >= 0.38:
            return "medium"
        return "low"

    @classmethod
    def _build_predictions(cls, strategy: Dict[str, Any], sections: List[Dict[str, str]], opinion: Dict[str, Any]) -> Dict[str, Any]:
        themes = []
        for index, topic in enumerate((opinion.get("hot_topics") or [])[:6], start=1):
            theme_id = topic.get("id") or f"theme_{index}"
            drivers = topic.get("driver_scores") or {}
            bar_names = ["声量", "风险", "机会", "未来", "证据"]
            bar_values = [
                drivers.get("engagement", 0.3),
                drivers.get("risk", 0.2),
                drivers.get("opportunity", 0.2),
                drivers.get("future", 0.3),
                drivers.get("evidence", 0.4),
            ]
            themes.append({
                "id": theme_id,
                "title": topic.get("title") or f"舆情主题 {index}",
                "confidence": float(topic.get("confidence") or topic.get("heat") or 0.55),
                "charts": [
                    {
                        "id": f"{theme_id}_heat",
                        "kind": "line_with_band",
                        "title": "未来 72h 舆情热度推演",
                        "data": _line_band(24, float(topic.get("heat") or 0.55), 0.18),
                    },
                    {
                        "id": f"{theme_id}_drivers",
                        "kind": "bar",
                        "title": "热点驱动因素权重",
                        "data": {"x": bar_names, "y": [round(float(v), 2) for v in bar_values]},
                    },
                ],
                "insight": cls._theme_insight(topic),
                "actions": cls._theme_actions(topic, strategy),
                "evidence_ids": topic.get("evidence_ids") or [],
            })
        return {"themes": themes}

    @classmethod
    def _theme_insight(cls, topic: Dict[str, Any]) -> str:
        layer = topic.get("source_layer") or "Inferred"
        keywords = "、".join((topic.get("keywords") or [])[:3])
        return f"该主题来自报告的 {layer} 层信号，当前热度 {int(float(topic.get('heat', 0.5)) * 100)}。关键词为 {keywords or '报告核心议题'}；后续主要观察评论区是否从信息扩散转向立场对抗。{topic.get('summary') or ''}"

    @classmethod
    def _theme_actions(cls, topic: Dict[str, Any], strategy: Dict[str, Any]) -> List[Dict[str, str]]:
        actions = [
            {"kind": "tactic", "text": f"围绕“{topic.get('title')}”追踪未来 24-72h 声量峰值、反方观点和二次转发节点。"},
            {"kind": "risk", "text": "如果风险/质疑类关键词继续升高，优先输出澄清型内容和合规风险提示。"},
        ]
        matches = strategy.get("product_matches") or []
        if matches:
            product = matches[0]
            actions.append({"kind": "allocate", "text": f"CSOP 策略层可同步评估 {product.get('product_name') or product.get('product')} 的客户沟通适配。"})
        return actions

    @classmethod
    def _build_posts_by_theme(cls, strategy: Dict[str, Any], opinion: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        stakeholders = opinion.get("stakeholders") or []
        for topic_index, topic in enumerate(opinion.get("hot_topics") or [], start=1):
            theme_id = topic.get("id") or f"theme_{topic_index}"
            posts = []
            for angle_index, angle in enumerate(ANGLE_CATALOG, start=1):
                stakeholder = stakeholders[(angle_index - 1) % len(stakeholders)] if stakeholders else {}
                body = cls._post_body(topic, angle["angle"], stakeholder, strategy)
                posts.append({
                    "id": f"post_{theme_id}_{angle['angle']}",
                    "angle": angle["angle"],
                    "angle_label": angle["label"],
                    "angle_tone": angle["tone"],
                    "persona_id": stakeholder.get("id") or "report_analyst",
                    "title": cls._post_title(topic, angle["angle"]),
                    "body": body,
                    "evidence_ids": topic.get("evidence_ids") or [],
                    "platform_variants": {
                        "twitter": _trim(body, 180),
                        "reddit": body,
                        "longform": body,
                    },
                })
            out[theme_id] = posts
        return out

    @classmethod
    def _post_title(cls, topic: Dict[str, Any], angle: str) -> str:
        title = topic.get("title") or "舆情主题"
        if angle == "news":
            return f"新闻解读：{title} 为什么成为下一轮热点"
        if angle == "commentary":
            return f"评论区脉络：围绕 {title} 的三类声音"
        return f"风险反方：{title} 可能被误读的地方"

    @classmethod
    def _post_body(cls, topic: Dict[str, Any], angle: str, stakeholder: Dict[str, Any], strategy: Dict[str, Any]) -> str:
        seed = topic.get("post_seed") or topic.get("summary") or topic.get("title") or "报告热点"
        seed = _sentence_stem(seed)
        stakeholder_name = stakeholder.get("name") or "主要利益相关方"
        if angle == "news":
            return f"基于 Step4 报告二次分析，{topic.get('title')} 的热度排名靠前，核心证据是：{seed}。短期内需要观察媒体标题、转发节点和评论区是否形成同向叙事。"
        if angle == "commentary":
            return f"从评论区视角看，{stakeholder_name} 会把“{topic.get('title')}”拆成机会、风险和行动窗口三条线。当前最值得追踪的是分歧是否从事实判断升级为立场对抗。"
        product_hint = ""
        matches = strategy.get("product_matches") or []
        if matches:
            product_hint = f" 同时，涉及产品沟通时可参考 {matches[0].get('product_name') or matches[0].get('product')} 的合规话术边界。"
        return f"反方风险在于：{topic.get('title')} 的高热度可能来自短期情绪放大，而不是基本面确认。需要把舆情声量、事实证据和行动建议分开处理，避免把推演结论包装成确定性判断。{product_hint}"
