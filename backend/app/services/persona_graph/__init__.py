"""
Persona Graph - 用户画像图谱模块

在 Zep 实体图谱之上，新增一层"用户画像图谱"层，把 OASIS 模拟群体映射到真实
CSOP 客户分群，最终以"便签卡片"形式呈现给执行层使用。

四层架构：
  Zep 实体图谱 (Layer A，保留不动)
       │ DERIVED_FROM
       ▼
  SimulatedPersona (Layer B - 模拟群体画像便签卡片)
       │ BELONGS_TO
       ▼
  PersonaCluster (Layer C - 聚类群组)
       │ MAPS_TO
       ▼
  InvestorSegment (Layer D - 真实客户分群)
       │
       ▼
  产品策略（执行层已有）

后端：Graphiti + FalkorDB（自托管）
"""

from .schema import (
    SimulatedPersona,
    PersonaCluster,
    InvestorSegment,
    RealClient,
    DerivedFrom,
    BelongsTo,
    MapsTo,
    Matches,
    EvolvedTo,
    Follows,
    SameGroupAs,
    InfluencedBy,
    PERSONA_ENTITY_TYPES,
    PERSONA_EDGE_TYPES,
)
from .client import get_graphiti, is_persona_graph_enabled, close_graphiti

__all__ = [
    'SimulatedPersona',
    'PersonaCluster',
    'InvestorSegment',
    'RealClient',
    'DerivedFrom',
    'BelongsTo',
    'MapsTo',
    'Matches',
    'EvolvedTo',
    'Follows',
    'SameGroupAs',
    'InfluencedBy',
    'PERSONA_ENTITY_TYPES',
    'PERSONA_EDGE_TYPES',
    'get_graphiti',
    'is_persona_graph_enabled',
    'close_graphiti',
]
