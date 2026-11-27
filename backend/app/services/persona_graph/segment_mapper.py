"""
Segment Mapper - 把 PersonaCluster 映射到 InvestorSegment

策略：
1. 规则优先：按 risk_appetite + portfolio_type 关键词命中 6 类 InvestorSegment
2. LLM 补全：规则未命中时调用 LLM 给出最相近的 InvestorSegment
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from ...utils.llm_client import LLMClient
from ...utils.logger import get_logger
from .client import get_graphiti, run_async
from .schema import PersonaCluster
from .seed_segments import INVESTOR_SEGMENTS_SEED

logger = get_logger('finrex.persona_graph.mapper')


@dataclass
class SegmentMapping:
    cluster_id: str
    segment_id: str
    segment_name: str
    confidence: float
    rationale: str


_SEGMENT_NAMES = {seg.segment_id: seg.name for seg in INVESTOR_SEGMENTS_SEED}


_MAPPER_SYSTEM_PROMPT = """你是金融客户分群映射专家。给定一个聚类与 6 类标准 CSOP 客户分群，
选择最匹配的 1 个分群。

可选 InvestorSegment：
- seg_aggressive: 积极型（高风险，科技/成长股）
- seg_conservative: 保守型（低风险，货币/短债）
- seg_dividend: 收息型（中等风险，高股息/REITs）
- seg_short_term: 短线交易型（高风险，主题/杠杆）
- seg_contrarian: 逆向型（中等风险，低估值/价值）
- seg_global: 全球配置型（中等风险，全球宽基/分散）

输出严格 JSON：{"segment_id": "...", "confidence": 0-1, "rationale": "..."}
不要输出 markdown 围栏。"""


class SegmentMapper:
    """聚类 → 客户分群映射器"""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self._llm: Optional[LLMClient] = None

    def _get_llm(self) -> Optional[LLMClient]:
        if not self.use_llm:
            return None
        if self._llm is None:
            try:
                self._llm = LLMClient()
            except Exception as exc:
                logger.warning(f"映射 LLM 不可用，降级为规则: {exc}")
                self._llm = None
        return self._llm

    def map_clusters(
        self,
        clusters: List[PersonaCluster],
    ) -> List[SegmentMapping]:
        results: List[SegmentMapping] = []
        for c in clusters:
            mapping = self._rule_map(c)
            if mapping is None:
                mapping = self._llm_map(c)
            if mapping is None:
                # 兜底：均衡型 → 全球配置
                mapping = SegmentMapping(
                    cluster_id=c.cluster_id or '',
                    segment_id='seg_global',
                    segment_name='全球配置型',
                    confidence=0.3,
                    rationale='规则与 LLM 均未命中，默认全球配置',
                )
            results.append(mapping)
        return results

    def _rule_map(self, c: PersonaCluster) -> Optional[SegmentMapping]:
        name_lower = (c.name or '').lower()
        traits = (c.centroid_traits or '').lower()
        full = name_lower + ' ' + traits

        rules = [
            ('seg_aggressive', ['积极', 'aggressive', '科技', 'tech', 'growth', 'high-']),
            ('seg_conservative', ['保守', 'conservative', '低风险', 'low-', '债券', 'bond']),
            ('seg_dividend', ['收息', 'dividend', '股息', 'reit', 'income']),
            ('seg_short_term', ['短线', 'short_term', 'short-term', '波段', '主题', 'theme']),
            ('seg_contrarian', ['逆向', 'contrarian', '价值', 'value', '低估']),
            ('seg_global', ['全球', 'global', '分散', 'balanced', 'mid-balanced']),
        ]
        for seg_id, keywords in rules:
            for kw in keywords:
                if kw in full:
                    return SegmentMapping(
                        cluster_id=c.cluster_id or '',
                        segment_id=seg_id,
                        segment_name=_SEGMENT_NAMES[seg_id],
                        confidence=0.75,
                        rationale=f"规则命中关键词 '{kw}'",
                    )
        return None

    def _llm_map(self, c: PersonaCluster) -> Optional[SegmentMapping]:
        llm = self._get_llm()
        if llm is None:
            return None
        try:
            payload = {
                'cluster_id': c.cluster_id,
                'name': c.name,
                'description': c.description,
                'centroid_traits': c.centroid_traits,
                'size': c.size,
            }
            data = llm.chat_json(
                messages=[
                    {"role": "system", "content": _MAPPER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            seg_id = data.get('segment_id')
            if seg_id not in _SEGMENT_NAMES:
                return None
            return SegmentMapping(
                cluster_id=c.cluster_id or '',
                segment_id=seg_id,
                segment_name=_SEGMENT_NAMES[seg_id],
                confidence=float(data.get('confidence') or 0.5),
                rationale=str(data.get('rationale') or ''),
            )
        except Exception as exc:
            logger.warning(f"LLM 映射失败 cluster={c.cluster_id}: {exc}")
            return None


# ============================================================
# 写图
# ============================================================


async def _write_mappings_async(
    graphiti,
    mappings: List[SegmentMapping],
    simulation_id: str,
) -> int:
    if not mappings:
        return 0
    lines = ["PersonaCluster MAPS_TO InvestorSegment 映射关系："]
    for m in mappings:
        lines.append(
            f"- 聚类 {m.cluster_id} 映射到 InvestorSegment {m.segment_id} "
            f"({m.segment_name})，置信度 {m.confidence:.2f}，依据：{m.rationale}"
        )
    try:
        await graphiti.add_episode(
            name=f"Cluster→Segment Mapping {simulation_id}",
            episode_body="\n".join(lines),
            source_description=f"OASIS simulation {simulation_id}",
            reference_time=datetime.now(),
            group_id=simulation_id,
        )
        return len(mappings)
    except Exception as exc:
        logger.warning(f"写入分群映射失败: {exc}")
        return 0


def write_mappings_to_graph(
    mappings: List[SegmentMapping],
    simulation_id: str,
) -> int:
    if not mappings:
        return 0
    graphiti = get_graphiti()
    if graphiti is None:
        return 0
    try:
        return run_async(_write_mappings_async(graphiti, mappings, simulation_id))
    except Exception as exc:
        logger.warning(f"写入映射失败: {exc}")
        return 0
