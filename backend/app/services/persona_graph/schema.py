"""
用户画像图谱 Schema 定义

使用 Pydantic 定义 Graphiti 自定义实体类型与边类型。
所有节点都建议带有 `confidence` 字段（LLM 推断字段）以便前端做视觉降级。

注意：Graphiti 自定义实体的字段会被 LLM 用作抽取目标；为了同时支持"程序化写入"
（我们直接构造好节点 add 进去），所有字段都设为可选并提供合理默认。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 节点类型 (Entity Types)
# ============================================================


class SimulatedPersona(BaseModel):
    """
    模拟群体画像 - 一张"便签卡片"
    
    每个 OASIS Agent 在画像图谱中对应一个 SimulatedPersona 节点。
    """
    # ---- 标识 ----
    persona_uuid: Optional[str] = Field(
        default=None, description="画像唯一 ID（外部分配，与 user_id 强绑定）"
    )
    agent_user_id: Optional[int] = Field(
        default=None, description="OASIS agent 的 user_id（reddit_profiles.json / twitter_profiles.csv 中的 user_id）"
    )
    simulation_id: Optional[str] = Field(
        default=None, description="所属模拟 ID"
    )
    source_entity_uuid: Optional[str] = Field(
        default=None, description="派生自的 Zep 实体 UUID"
    )
    source_entity_type: Optional[str] = Field(
        default=None, description="派生自的 Zep 实体类型（如 Media、GovernmentAgency）"
    )
    name: Optional[str] = Field(default=None, description="人设姓名")

    # ---- 人口学 ----
    age: Optional[int] = Field(default=None, description="年龄")
    gender: Optional[str] = Field(default=None, description="性别 male/female/other")
    country: Optional[str] = Field(default=None, description="国家或地区")
    profession: Optional[str] = Field(default=None, description="职业")

    # ---- 心理学 ----
    mbti: Optional[str] = Field(default=None, description="MBTI 类型，例如 INTJ")
    big5_openness: Optional[float] = Field(default=None, description="Big5 开放性 0-1")
    big5_conscientiousness: Optional[float] = Field(default=None, description="Big5 尽责性 0-1")
    big5_extraversion: Optional[float] = Field(default=None, description="Big5 外向性 0-1")
    big5_agreeableness: Optional[float] = Field(default=None, description="Big5 宜人性 0-1")
    big5_neuroticism: Optional[float] = Field(default=None, description="Big5 神经质 0-1")
    risk_appetite: Optional[str] = Field(
        default=None, description="风险偏好 low / mid / high"
    )

    # ---- 投资属性 ----
    risk_level: Optional[str] = Field(
        default=None, description="风险等级 R1-R5 或 conservative/balanced/aggressive"
    )
    portfolio_type: Optional[str] = Field(
        default=None, description="持仓风格，如 'tech_growth' / 'dividend_income' / 'balanced'"
    )
    return_preference: Optional[str] = Field(
        default=None, description="收益偏好 capital_gain / dividend / mixed"
    )
    time_horizon: Optional[str] = Field(
        default=None, description="投资期限 short / mid / long"
    )

    # ---- 行为偏好 ----
    interested_topics: List[str] = Field(default_factory=list, description="关注话题列表")
    preferred_media: List[str] = Field(default_factory=list, description="偏好媒体渠道")
    active_hours: List[str] = Field(default_factory=list, description="活跃时段")

    # ---- 动态信号（随模拟过程演化）----
    sentiment_trajectory: List[float] = Field(
        default_factory=list,
        description="情绪轨迹时序（每个 timestep 一个值，-1 到 1）",
    )
    topic_switch_log: List[str] = Field(
        default_factory=list, description="话题切换日志"
    )
    polarization_score: Optional[float] = Field(
        default=None, description="极化得分 0-1，越大越极化"
    )

    # ---- 可信度 ----
    confidence: Optional[float] = Field(
        default=None, description="LLM 推断字段的整体置信度 0-1"
    )

    # ---- 摘要文本 ----
    summary: Optional[str] = Field(
        default=None, description="人设摘要文本，便签卡片正面展示"
    )


class PersonaCluster(BaseModel):
    """聚类群组 - 多个 SimulatedPersona 聚成一群"""
    cluster_id: Optional[str] = Field(default=None, description="聚类 ID")
    simulation_id: Optional[str] = Field(default=None, description="所属模拟 ID")
    name: Optional[str] = Field(default=None, description='聚类名称，如"科技积极型"')
    description: Optional[str] = Field(default=None, description="聚类描述")
    size: Optional[int] = Field(default=None, description="成员数量")
    centroid_traits: Optional[str] = Field(
        default=None, description="质心特征摘要（自然语言）"
    )
    representative_persona_uuids: List[str] = Field(
        default_factory=list, description="代表性 persona UUID 列表"
    )


class InvestorSegment(BaseModel):
    """真实客户分群 - 对应 CSOP 已有的客户画像类型"""
    segment_id: Optional[str] = Field(default=None, description="分群 ID")
    name: Optional[str] = Field(
        default=None,
        description="分群名称，如：积极型 / 保守型 / 收息型 / 短线 / 逆向 / 全球配置",
    )
    risk_appetite: Optional[str] = Field(default=None, description="风险偏好 low/mid/high")
    description: Optional[str] = Field(default=None, description="分群描述")
    recommended_products: List[str] = Field(
        default_factory=list, description="推荐产品列表"
    )
    talking_points: List[str] = Field(
        default_factory=list, description="销售切入点 / 卖点话术"
    )


class RealClient(BaseModel):
    """真实 CRM 客户（占位，用于后续 CRM 数据接入）"""
    client_id: Optional[str] = Field(default=None, description="脱敏后的客户 ID")
    anonymized_profile: Optional[str] = Field(
        default=None, description="脱敏后的客户画像描述"
    )
    current_holdings: List[str] = Field(
        default_factory=list, description="当前持仓列表（脱敏）"
    )


# ============================================================
# 边类型 (Edge Types)
# ============================================================


class DerivedFrom(BaseModel):
    """SimulatedPersona → Zep Entity（保留可追溯性）"""
    extraction_method: Optional[str] = Field(
        default=None, description="抽取方法 entity_only / entity_plus_llm"
    )
    extracted_at: Optional[str] = Field(default=None, description="抽取时间")


class BelongsTo(BaseModel):
    """SimulatedPersona → PersonaCluster"""
    similarity: Optional[float] = Field(default=None, description="与质心相似度 0-1")


class MapsTo(BaseModel):
    """PersonaCluster → InvestorSegment（关键映射）"""
    confidence: Optional[float] = Field(default=None, description="映射置信度 0-1")
    rationale: Optional[str] = Field(default=None, description="映射依据")


class Matches(BaseModel):
    """RealClient → InvestorSegment"""
    confidence: Optional[float] = Field(default=None, description="匹配置信度 0-1")


class EvolvedTo(BaseModel):
    """SimulatedPersona@t1 → SimulatedPersona@t2（时序演化）"""
    timestep: Optional[int] = Field(default=None, description="时间步")
    delta_summary: Optional[str] = Field(default=None, description="变化摘要")


class Follows(BaseModel):
    """模拟社交：A 关注 B"""
    weight: Optional[float] = Field(default=None, description="关系强度")


class SameGroupAs(BaseModel):
    """模拟社交：A 与 B 同群"""
    pass


class InfluencedBy(BaseModel):
    """模拟社交：A 受 B 影响"""
    influence_score: Optional[float] = Field(default=None, description="影响分数")


# ============================================================
# 注册到 Graphiti 的类型字典
# ============================================================

PERSONA_ENTITY_TYPES = {
    'SimulatedPersona': SimulatedPersona,
    'PersonaCluster': PersonaCluster,
    'InvestorSegment': InvestorSegment,
    'RealClient': RealClient,
}

PERSONA_EDGE_TYPES = {
    'DERIVED_FROM': DerivedFrom,
    'BELONGS_TO': BelongsTo,
    'MAPS_TO': MapsTo,
    'MATCHES': Matches,
    'EVOLVED_TO': EvolvedTo,
    'FOLLOWS': Follows,
    'SAME_GROUP_AS': SameGroupAs,
    'INFLUENCED_BY': InfluencedBy,
}
