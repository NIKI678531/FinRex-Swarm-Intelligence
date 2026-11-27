"""
Persona Pipeline - 端到端编排（抽取 → 写图 → 聚类 → 映射 → 持久化 sidecar）

由 simulation_manager 在 profile 生成阶段调用。
任何子步骤失败均不抛出，确保画像图谱失败不阻塞主模拟流程。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from ..oasis_profile_generator import OasisAgentProfile
from .client import is_persona_graph_enabled
from .cluster_engine import ClusterEngine, write_clusters_to_graph
from .persona_extractor import (
    PersonaExtractor,
    build_profile_index,
    write_personas_to_graph,
)
from .schema import SimulatedPersona
from .segment_mapper import SegmentMapper, write_mappings_to_graph

logger = get_logger('finrex.persona_graph.pipeline')


def run_persona_pipeline(
    profiles: List[OasisAgentProfile],
    simulation_id: str,
    sim_dir: str,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    跑完整画像图谱构建管线。

    Args:
        profiles: OasisAgentProfile 列表（来自 OasisProfileGenerator）
        simulation_id: 模拟 ID
        sim_dir: 模拟目录，用于写 profile_index.json sidecar
        use_llm: 是否调用 LLM（推断/聚类/映射）

    Returns:
        摘要字典，包含 personas_count / clusters_count / segments / enabled
    """
    summary: Dict[str, Any] = {
        'enabled': False,
        'personas_count': 0,
        'clusters_count': 0,
        'segment_mappings': [],
        'profile_index_path': None,
        'errors': [],
    }

    if not profiles:
        return summary

    enabled = is_persona_graph_enabled()
    summary['enabled'] = enabled

    # ---- 即使 graph 后端未启用，也至少抽取并写 sidecar ----
    personas: List[SimulatedPersona] = []
    try:
        extractor = PersonaExtractor(use_llm=use_llm)
        for prof in profiles:
            try:
                p = extractor.extract(prof, simulation_id=simulation_id)
                personas.append(p)
            except Exception as exc:
                logger.warning(f"抽取画像失败 user_id={prof.user_id}: {exc}")
                summary['errors'].append(f"extract:{prof.user_id}:{exc}")
    except Exception as exc:
        logger.warning(f"画像抽取阶段失败: {exc}")
        summary['errors'].append(f"extract_phase:{exc}")
        return summary

    summary['personas_count'] = len(personas)

    # ---- 写 sidecar ----
    try:
        index = build_profile_index(personas, profiles)
        sidecar_path = os.path.join(sim_dir, 'profile_index.json')
        with open(sidecar_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        summary['profile_index_path'] = sidecar_path
        logger.info(f"profile_index.json 已生成: {sidecar_path}")
    except Exception as exc:
        logger.warning(f"写 profile_index.json 失败: {exc}")
        summary['errors'].append(f"sidecar:{exc}")

    # ---- 后端未启用 → 到此为止 ----
    if not enabled:
        logger.info("画像图谱后端未启用，跳过写图与聚类")
        return summary

    # ---- 写画像到 Graphiti ----
    try:
        written = write_personas_to_graph(personas)
        logger.info(f"已写入 {written}/{len(personas)} 个 SimulatedPersona 到画像图谱")
    except Exception as exc:
        logger.warning(f"写画像到图谱失败: {exc}")
        summary['errors'].append(f"write_personas:{exc}")

    # ---- 聚类 ----
    try:
        engine = ClusterEngine(use_llm=use_llm)
        cluster_result = engine.cluster(personas, simulation_id=simulation_id)
        summary['clusters_count'] = len(cluster_result.clusters)
        write_clusters_to_graph(cluster_result, simulation_id=simulation_id)
    except Exception as exc:
        logger.warning(f"聚类阶段失败: {exc}")
        summary['errors'].append(f"cluster:{exc}")
        cluster_result = None

    # ---- 客户分群映射 ----
    if cluster_result and cluster_result.clusters:
        try:
            mapper = SegmentMapper(use_llm=use_llm)
            mappings = mapper.map_clusters(cluster_result.clusters)
            write_mappings_to_graph(mappings, simulation_id=simulation_id)
            summary['segment_mappings'] = [
                {
                    'cluster_id': m.cluster_id,
                    'segment_id': m.segment_id,
                    'segment_name': m.segment_name,
                    'confidence': m.confidence,
                    'rationale': m.rationale,
                }
                for m in mappings
            ]
        except Exception as exc:
            logger.warning(f"分群映射阶段失败: {exc}")
            summary['errors'].append(f"map:{exc}")

    return summary
