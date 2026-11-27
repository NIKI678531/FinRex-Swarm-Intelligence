"""
Cluster Engine - 画像聚类

输入：SimulatedPersona 列表
输出：PersonaCluster 列表 + BELONGS_TO 边

策略（优先 LLM-based 聚类，无 LLM 时降级为规则聚类）：
- LLM 模式：把所有画像精简描述发给 LLM，让其产出 3-8 个聚类及成员归属
- 规则模式：按 (risk_appetite, portfolio_type) 二维笛卡尔分桶，再合并 size<2 的桶
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ...utils.llm_client import LLMClient
from ...utils.logger import get_logger
from .client import get_graphiti, run_async
from .schema import PersonaCluster, SimulatedPersona

logger = get_logger('finrex.persona_graph.cluster')


_CLUSTER_SYSTEM_PROMPT = """你是金融客户分群专家。给定一组模拟用户画像，将他们聚类成 3-6 个有代表性的"投资人群"。

输出严格的 JSON 数组，每个元素结构：
{
  "cluster_id": "cl_<短英文>",
  "name": "聚类中文名（如 '科技积极型'）",
  "description": "100 字以内描述",
  "centroid_traits": "质心特征摘要",
  "members": [persona_uuid 列表]
}
要求：
- 所有画像必须被分配到某个聚类，不能遗漏
- 每个聚类至少 1 个成员
- 名称应能直接对接 CSOP 的客户分群（积极型/保守型/收息型/短线/逆向/全球配置）
不要输出 markdown 代码块。"""


@dataclass
class ClusterResult:
    clusters: List[PersonaCluster]
    membership: Dict[str, str]  # persona_uuid -> cluster_id


class ClusterEngine:
    """画像聚类引擎"""

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
                logger.warning(f"聚类 LLM 不可用，降级为规则聚类: {exc}")
                self._llm = None
        return self._llm

    def cluster(
        self,
        personas: List[SimulatedPersona],
        simulation_id: str,
    ) -> ClusterResult:
        if not personas:
            return ClusterResult(clusters=[], membership={})

        result = self._llm_cluster(personas, simulation_id)
        if result is None:
            result = self._rule_cluster(personas, simulation_id)
        return result

    # ----- LLM 聚类 -----
    def _llm_cluster(
        self,
        personas: List[SimulatedPersona],
        simulation_id: str,
    ) -> Optional[ClusterResult]:
        llm = self._get_llm()
        if llm is None:
            return None

        rows = []
        for p in personas:
            rows.append({
                'persona_uuid': p.persona_uuid,
                'profession': p.profession,
                'age': p.age,
                'risk_appetite': p.risk_appetite,
                'risk_level': p.risk_level,
                'portfolio_type': p.portfolio_type,
                'interested_topics': p.interested_topics,
                'summary': p.summary,
            })

        try:
            raw = llm.chat(
                messages=[
                    {"role": "system", "content": _CLUSTER_SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"模拟 ID: {simulation_id}\n"
                        f"共 {len(rows)} 个画像，请聚类：\n"
                        + json.dumps(rows, ensure_ascii=False, indent=2)
                    )},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            data = _parse_json_array(raw)
            if not isinstance(data, list) or not data:
                return None

            clusters: List[PersonaCluster] = []
            membership: Dict[str, str] = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                cid = item.get('cluster_id') or f"cl_{len(clusters)}"
                members = item.get('members') or []
                clusters.append(PersonaCluster(
                    cluster_id=cid,
                    simulation_id=simulation_id,
                    name=item.get('name'),
                    description=item.get('description'),
                    centroid_traits=item.get('centroid_traits'),
                    size=len(members),
                    representative_persona_uuids=members[:3],
                ))
                for m in members:
                    membership[m] = cid
            return ClusterResult(clusters=clusters, membership=membership)
        except Exception as exc:
            logger.warning(f"LLM 聚类失败，回退规则聚类: {exc}")
            return None

    # ----- 规则聚类 -----
    def _rule_cluster(
        self,
        personas: List[SimulatedPersona],
        simulation_id: str,
    ) -> ClusterResult:
        buckets: Dict[Tuple[str, str], List[str]] = {}
        for p in personas:
            key = (p.risk_appetite or 'mid', p.portfolio_type or 'balanced')
            buckets.setdefault(key, []).append(p.persona_uuid or '')

        clusters: List[PersonaCluster] = []
        membership: Dict[str, str] = {}
        for idx, ((risk, ptype), members) in enumerate(buckets.items()):
            cid = f"cl_{simulation_id}_{idx}"
            name = f"{risk}-{ptype}"
            clusters.append(PersonaCluster(
                cluster_id=cid,
                simulation_id=simulation_id,
                name=name,
                description=f"风险偏好={risk}，持仓风格={ptype}",
                centroid_traits=f"risk_appetite={risk}; portfolio_type={ptype}",
                size=len(members),
                representative_persona_uuids=members[:3],
            ))
            for m in members:
                if m:
                    membership[m] = cid
        return ClusterResult(clusters=clusters, membership=membership)


# ============================================================
# 写图：将聚类与 BELONGS_TO 边写入 Graphiti
# ============================================================


async def _write_clusters_async(
    graphiti,
    result: ClusterResult,
    simulation_id: str,
) -> int:
    written = 0
    for c in result.clusters:
        text = (
            f"PersonaCluster 聚类档案：\n"
            f"聚类 ID: {c.cluster_id}\n"
            f"所属模拟: {c.simulation_id}\n"
            f"聚类名称: {c.name}\n"
            f"聚类规模: {c.size}\n"
            f"质心特征: {c.centroid_traits}\n"
            f"描述: {c.description}\n"
            f"代表画像: {', '.join(c.representative_persona_uuids)}\n"
        )
        try:
            await graphiti.add_episode(
                name=f"PersonaCluster {c.cluster_id}",
                episode_body=text,
                source_description=f"OASIS simulation {simulation_id}",
                reference_time=datetime.now(),
                group_id=simulation_id,
            )
            written += 1
        except Exception as exc:
            logger.warning(f"写入聚类 {c.cluster_id} 失败: {exc}")

    # BELONGS_TO 关系（自然语言描述，让 Graphiti 抽取边）
    if result.membership:
        membership_lines = [
            "SimulatedPersona BELONGS_TO PersonaCluster 归属关系："
        ]
        for puuid, cid in result.membership.items():
            membership_lines.append(f"- 画像 {puuid} 属于聚类 {cid}")
        try:
            await graphiti.add_episode(
                name=f"Cluster Membership {simulation_id}",
                episode_body="\n".join(membership_lines),
                source_description=f"OASIS simulation {simulation_id}",
                reference_time=datetime.now(),
                group_id=simulation_id,
            )
        except Exception as exc:
            logger.warning(f"写入聚类归属关系失败: {exc}")
    return written


def write_clusters_to_graph(result: ClusterResult, simulation_id: str) -> int:
    if not result.clusters:
        return 0
    graphiti = get_graphiti()
    if graphiti is None:
        return 0
    try:
        return run_async(_write_clusters_async(graphiti, result, simulation_id))
    except Exception as exc:
        logger.warning(f"写入聚类失败: {exc}")
        return 0


def _parse_json_array(text: str):
    """容错解析 JSON 数组，剥离可能的 markdown 包裹"""
    s = text.strip()
    if s.startswith('```'):
        # 去除围栏
        lines = s.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        s = '\n'.join(lines).strip()
    # 找第一个 [ 与最后一个 ]
    start = s.find('[')
    end = s.rfind(']')
    if start >= 0 and end > start:
        s = s[start:end + 1]
    return json.loads(s)
