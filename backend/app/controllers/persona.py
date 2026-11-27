"""
Persona Graph API - 用户画像图谱接口

为前端"便签卡片墙"提供数据源。
当画像图谱后端未启用时，回退到读取 simulation 目录下的 profile_index.json sidecar。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify

from ..config import Config
from ..services.persona_graph.client import (
    is_persona_graph_enabled,
)
from ..services.persona_graph.seed_segments import INVESTOR_SEGMENTS_SEED
from ..utils.logger import get_logger

logger = get_logger('finrex.api.persona')

persona_bp = Blueprint('persona', __name__)


def _sim_dir(simulation_id: str) -> str:
    return os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)


def _load_profile_index(simulation_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_sim_dir(simulation_id), 'profile_index.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"读取 profile_index.json 失败: {exc}")
        return None


def _load_oasis_profiles(simulation_id: str) -> List[Dict[str, Any]]:
    """合并读取 reddit_profiles.json / twitter_profiles.csv 中的字段，按 user_id 索引"""
    sim_dir = _sim_dir(simulation_id)
    by_uid: Dict[int, Dict[str, Any]] = {}

    reddit_path = os.path.join(sim_dir, 'reddit_profiles.json')
    if os.path.exists(reddit_path):
        try:
            with open(reddit_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data if isinstance(data, list) else []:
                uid = item.get('user_id')
                if uid is not None:
                    by_uid[uid] = {**by_uid.get(uid, {}), **item}
        except Exception as exc:
            logger.debug(f"读取 reddit_profiles.json 失败: {exc}")

    twitter_path = os.path.join(sim_dir, 'twitter_profiles.csv')
    if os.path.exists(twitter_path):
        try:
            import csv
            with open(twitter_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        uid = int(row.get('user_id') or 0)
                    except ValueError:
                        continue
                    by_uid[uid] = {**by_uid.get(uid, {}), **row}
        except Exception as exc:
            logger.debug(f"读取 twitter_profiles.csv 失败: {exc}")

    return list(by_uid.values())


# ============================================================
# 端点
# ============================================================


@persona_bp.route('/<simulation_id>/list', methods=['GET'])
def list_personas(simulation_id: str):
    """列出某模拟的所有 SimulatedPersona（便签卡片数据）"""
    index = _load_profile_index(simulation_id)
    profiles = _load_oasis_profiles(simulation_id)
    profiles_by_uid = {
        p.get('user_id'): p for p in profiles if p.get('user_id') is not None
    }
    if isinstance(profiles_by_uid, dict):
        # 把 string user_id 也归一化
        normalized = {}
        for k, v in profiles_by_uid.items():
            try:
                normalized[int(k)] = v
            except (TypeError, ValueError):
                pass
        profiles_by_uid = normalized

    cards: List[Dict[str, Any]] = []
    if index and isinstance(index.get('entries'), list):
        for entry in index['entries']:
            uid = entry.get('user_id')
            base = profiles_by_uid.get(uid, {}) if uid is not None else {}
            cards.append({
                'persona_uuid': entry.get('persona_uuid'),
                'user_id': uid,
                'user_name': entry.get('user_name') or base.get('username'),
                'name': entry.get('name') or base.get('name'),
                'profession': base.get('profession'),
                'age': base.get('age'),
                'gender': base.get('gender'),
                'country': base.get('country'),
                'mbti': base.get('mbti'),
                'interested_topics': base.get('interested_topics') or [],
                'bio': base.get('bio'),
                'risk_appetite': entry.get('risk_appetite'),
                'portfolio_type': entry.get('portfolio_type'),
                'confidence': entry.get('confidence'),
                'source_entity_uuid': entry.get('source_entity_uuid'),
                'source_entity_type': entry.get('source_entity_type'),
            })
    else:
        # Sidecar 缺失：直接基于 oasis profile 渲染
        for p in profiles:
            uid = p.get('user_id')
            cards.append({
                'persona_uuid': f"persona_{simulation_id}_{uid}" if uid is not None else None,
                'user_id': uid,
                'user_name': p.get('username'),
                'name': p.get('name'),
                'profession': p.get('profession'),
                'age': p.get('age'),
                'gender': p.get('gender'),
                'country': p.get('country'),
                'mbti': p.get('mbti'),
                'interested_topics': p.get('interested_topics') or [],
                'bio': p.get('bio'),
                'risk_appetite': None,
                'portfolio_type': None,
                'confidence': None,
                'source_entity_uuid': None,
                'source_entity_type': None,
            })

    return jsonify({
        'simulation_id': simulation_id,
        'count': len(cards),
        'cards': cards,
        'graph_enabled': is_persona_graph_enabled(),
        'has_index': index is not None,
    })


@persona_bp.route('/<simulation_id>/segments', methods=['GET'])
def get_segments(simulation_id: str):
    """返回 6 类标准 InvestorSegment + 该模拟的映射结果"""
    seeds = [
        {
            'segment_id': s.segment_id,
            'name': s.name,
            'risk_appetite': s.risk_appetite,
            'description': s.description,
            'recommended_products': s.recommended_products,
            'talking_points': s.talking_points,
        }
        for s in INVESTOR_SEGMENTS_SEED
    ]
    # 映射结果存在于 Graphiti（当前回合写入了 Mapping episode）；
    # 回退方案：若有 cached summary 在 sim_dir，则读它
    mappings_path = os.path.join(_sim_dir(simulation_id), 'persona_segment_mappings.json')
    mappings: List[Dict[str, Any]] = []
    if os.path.exists(mappings_path):
        try:
            with open(mappings_path, 'r', encoding='utf-8') as f:
                mappings = json.load(f) or []
        except Exception:
            pass

    return jsonify({
        'simulation_id': simulation_id,
        'segments': seeds,
        'mappings': mappings,
    })


