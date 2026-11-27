"""
Persona Extractor - 从 OasisAgentProfile 派生 SimulatedPersona

输入：OasisAgentProfile（已生成）+ 可选的 Zep 实体上下文
输出：完整 SimulatedPersona 节点 + DERIVED_FROM 边

策略：
1. 直接复用已生成字段（age/gender/mbti/country/profession/interested_topics）
2. LLM 推断缺失维度（Big5、risk_appetite、risk_level、portfolio_type、
   return_preference、time_horizon），附 confidence
3. 失败时降级为规则推断 + 标低置信度
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.llm_client import LLMClient
from ...utils.logger import get_logger
from ..oasis_profile_generator import OasisAgentProfile
from .client import get_graphiti, run_async
from .schema import SimulatedPersona

logger = get_logger('finrex.persona_graph.extractor')


_INFERENCE_SYSTEM_PROMPT = """你是一名金融用户画像分析师。基于给定的 OASIS 模拟 Agent 资料，
推断该用户在投资场景下的心理学和投资属性维度。

严格输出 JSON 对象，字段如下（值为 null 表示无法判断）：
{
  "big5_openness": 0-1 浮点数,
  "big5_conscientiousness": 0-1 浮点数,
  "big5_extraversion": 0-1 浮点数,
  "big5_agreeableness": 0-1 浮点数,
  "big5_neuroticism": 0-1 浮点数,
  "risk_appetite": "low" | "mid" | "high",
  "risk_level": "R1" | "R2" | "R3" | "R4" | "R5",
  "portfolio_type": 字符串描述,
  "return_preference": "capital_gain" | "dividend" | "mixed",
  "time_horizon": "short" | "mid" | "long",
  "confidence": 0-1 浮点数,
  "summary": "30 字以内便签卡正面摘要"
}
不要输出 markdown 代码块，直接给纯 JSON。"""


class PersonaExtractor:
    """画像抽取器"""

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
                logger.warning(f"LLMClient 初始化失败，画像抽取降级为规则模式: {exc}")
                self._llm = None
        return self._llm

    def extract(
        self,
        profile: OasisAgentProfile,
        simulation_id: str,
        zep_entity_context: Optional[str] = None,
    ) -> SimulatedPersona:
        """从单个 OasisAgentProfile 抽取 SimulatedPersona"""
        persona_uuid = f"persona_{simulation_id}_{profile.user_id}"

        base = SimulatedPersona(
            persona_uuid=persona_uuid,
            agent_user_id=profile.user_id,
            simulation_id=simulation_id,
            source_entity_uuid=profile.source_entity_uuid,
            source_entity_type=profile.source_entity_type,
            name=profile.name,
            age=profile.age,
            gender=_normalize_gender(profile.gender),
            country=profile.country,
            profession=profile.profession,
            mbti=profile.mbti,
            interested_topics=list(profile.interested_topics or []),
        )

        # LLM 推断
        inferred = self._llm_infer(profile, zep_entity_context)
        if inferred:
            for key, value in inferred.items():
                if value is None:
                    continue
                if hasattr(base, key):
                    setattr(base, key, value)

        # 兜底：若 LLM 没给 risk_appetite，规则推断
        if not base.risk_appetite:
            base.risk_appetite = _rule_infer_risk_appetite(profile)
            if base.confidence is None:
                base.confidence = 0.4

        if not base.summary:
            base.summary = _short_summary(profile)

        return base

    def _llm_infer(
        self,
        profile: OasisAgentProfile,
        zep_entity_context: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        llm = self._get_llm()
        if llm is None:
            return None

        user_prompt = _build_user_prompt(profile, zep_entity_context)
        try:
            result = llm.chat_json(
                messages=[
                    {"role": "system", "content": _INFERENCE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            if isinstance(result, dict):
                return result
        except Exception as exc:
            logger.warning(f"LLM 画像推断失败 user_id={profile.user_id}: {exc}")
        return None


# ============================================================
# 写图：批量将 SimulatedPersona 写入 Graphiti（含 DERIVED_FROM 边）
# ============================================================


async def _write_personas_async(graphiti, personas: List[SimulatedPersona]) -> int:
    written = 0
    for p in personas:
        text = _persona_to_episode_text(p)
        try:
            await graphiti.add_episode(
                name=f"SimulatedPersona {p.persona_uuid}",
                episode_body=text,
                source_description=f"OASIS simulation {p.simulation_id}",
                reference_time=datetime.now(),
                group_id=p.simulation_id or 'default',
            )
            written += 1
        except Exception as exc:
            logger.warning(
                f"写入 SimulatedPersona {p.persona_uuid} 失败: {exc}"
            )
    return written


def write_personas_to_graph(personas: List[SimulatedPersona]) -> int:
    """批量写入画像到 Graphiti；图谱未启用时返回 0"""
    if not personas:
        return 0
    graphiti = get_graphiti()
    if graphiti is None:
        return 0
    try:
        return run_async(_write_personas_async(graphiti, personas))
    except Exception as exc:
        logger.warning(f"批量写入画像失败: {exc}")
        return 0


# ============================================================
# 工具函数
# ============================================================


def _build_user_prompt(
    profile: OasisAgentProfile,
    zep_entity_context: Optional[str],
) -> str:
    parts = [
        f"Agent 资料：",
        f"- 姓名: {profile.name}",
        f"- 用户名: {profile.user_name}",
        f"- 年龄: {profile.age}",
        f"- 性别: {profile.gender}",
        f"- 国家: {profile.country}",
        f"- 职业: {profile.profession}",
        f"- MBTI: {profile.mbti}",
        f"- 关注话题: {', '.join(profile.interested_topics or []) or '无'}",
        f"- 简介: {profile.bio}",
        f"- 详细人设: {(profile.persona or '')[:600]}",
    ]
    if zep_entity_context:
        parts.append("\n来自图谱的上下文：")
        parts.append(zep_entity_context[:800])
    parts.append("\n请输出推断 JSON。")
    return "\n".join(parts)


def _normalize_gender(g: Optional[str]) -> Optional[str]:
    if not g:
        return None
    s = g.strip().lower()
    if s in ('m', 'male', '男'):
        return 'male'
    if s in ('f', 'female', '女'):
        return 'female'
    return 'other'


def _rule_infer_risk_appetite(profile: OasisAgentProfile) -> str:
    """简易规则：年龄越大越保守，特定职业偏激进"""
    age = profile.age or 35
    profession = (profile.profession or '').lower()
    aggressive_kw = ('trader', 'analyst', 'startup', 'crypto', 'venture', 'tech')
    conservative_kw = ('retire', 'teacher', 'civil', 'doctor', 'official')

    if any(k in profession for k in aggressive_kw):
        return 'high'
    if any(k in profession for k in conservative_kw):
        return 'low'
    if age >= 55:
        return 'low'
    if age <= 30:
        return 'high'
    return 'mid'


def _short_summary(profile: OasisAgentProfile) -> str:
    pieces = []
    if profile.profession:
        pieces.append(profile.profession)
    if profile.age:
        pieces.append(f"{profile.age}岁")
    if profile.country:
        pieces.append(profile.country)
    if profile.interested_topics:
        pieces.append("/".join(profile.interested_topics[:2]))
    return " · ".join(pieces) or (profile.name or '未命名画像')


def _persona_to_episode_text(p: SimulatedPersona) -> str:
    """把 SimulatedPersona 序列化成给 Graphiti 抽取用的自然语言"""
    lines = [
        f"SimulatedPersona 用户画像档案：",
        f"画像 UUID: {p.persona_uuid}",
        f"Agent user_id: {p.agent_user_id}",
        f"所属模拟: {p.simulation_id}",
        f"来源实体 UUID: {p.source_entity_uuid}",
        f"来源实体类型: {p.source_entity_type}",
        f"姓名: {p.name}",
        f"年龄: {p.age}",
        f"性别: {p.gender}",
        f"国家: {p.country}",
        f"职业: {p.profession}",
        f"MBTI: {p.mbti}",
        f"风险偏好: {p.risk_appetite}",
        f"风险等级: {p.risk_level}",
        f"持仓风格: {p.portfolio_type}",
        f"收益偏好: {p.return_preference}",
        f"投资期限: {p.time_horizon}",
        f"关注话题: {', '.join(p.interested_topics)}",
        f"摘要: {p.summary}",
        f"置信度: {p.confidence}",
    ]
    if p.big5_openness is not None:
        lines.append(
            f"Big5: O={p.big5_openness} C={p.big5_conscientiousness} "
            f"E={p.big5_extraversion} A={p.big5_agreeableness} N={p.big5_neuroticism}"
        )
    return "\n".join(lines)


def build_profile_index(
    personas: List[SimulatedPersona],
    profiles: List[OasisAgentProfile],
) -> Dict[str, Any]:
    """
    构造 profile_index.json sidecar 内容。
    保存 user_id ↔ persona_uuid ↔ source_entity_uuid 映射，
    弥补 reddit_profiles.json / twitter_profiles.csv 序列化时丢失的字段。
    """
    persona_by_uid = {p.agent_user_id: p for p in personas}
    entries = []
    for prof in profiles:
        persona = persona_by_uid.get(prof.user_id)
        entries.append({
            'user_id': prof.user_id,
            'user_name': prof.user_name,
            'name': prof.name,
            'persona_uuid': persona.persona_uuid if persona else None,
            'source_entity_uuid': prof.source_entity_uuid,
            'source_entity_type': prof.source_entity_type,
            'risk_appetite': persona.risk_appetite if persona else None,
            'portfolio_type': persona.portfolio_type if persona else None,
            'confidence': persona.confidence if persona else None,
        })
    return {
        'version': 1,
        'generated_at': datetime.now().isoformat(),
        'count': len(entries),
        'entries': entries,
    }
