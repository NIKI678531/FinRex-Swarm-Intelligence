"""
Behavior Signal Writer - 把模拟行为信号写回到 SimulatedPersona

由 ZepGraphMemoryUpdater 在批量发送 Zep 活动后调用（双写）。
将每个 batch 的行为聚合为情绪/话题/极化信号，更新到 Graphiti 中
对应 SimulatedPersona 的动态字段（追加 sentiment_trajectory/topic_switch_log）。

任何失败都不抛出，只记日志。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from .client import get_graphiti, run_async

logger = get_logger('finrex.persona_graph.signal')


# 简易情绪关键词词典（中文 + 英文），用于无 LLM 时的轻量打分
_POSITIVE_KW = (
    '看好', '上涨', '突破', '利好', '强劲', '增长', '机会', '推荐',
    'bull', 'rally', 'gain', 'rise', 'good', 'great', 'win', 'profit', 'buy'
)
_NEGATIVE_KW = (
    '下跌', '崩盘', '利空', '风险', '亏损', '担忧', '抛售', '危机',
    'bear', 'crash', 'loss', 'fall', 'bad', 'sell', 'risk', 'concern', 'panic'
)


def _quick_sentiment(text: str) -> float:
    """简易词典打分，输出 -1 ~ 1"""
    if not text:
        return 0.0
    s = text.lower()
    pos = sum(1 for kw in _POSITIVE_KW if kw in s)
    neg = sum(1 for kw in _NEGATIVE_KW if kw in s)
    if pos + neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / (pos + neg)))


def _extract_topic_keywords(text: str) -> List[str]:
    """从文本提取候选话题关键词（粗粒度）"""
    if not text:
        return []
    # 中文：抓 2-4 字常见名词；英文：单词
    cn = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
    en = re.findall(r'\b[A-Za-z]{4,}\b', text)
    # 去重保序
    seen = set()
    out = []
    for k in cn + en:
        if k not in seen:
            seen.add(k)
            out.append(k)
        if len(out) >= 5:
            break
    return out


async def _write_signals_async(
    graphiti,
    activities_payload: List[Dict[str, Any]],
    simulation_id: str,
    platform: str,
) -> int:
    """
    写一条聚合的行为信号 episode 到 Graphiti，
    通过自然语言描述让 Graphiti 把信号关联到对应 SimulatedPersona。
    """
    if not activities_payload:
        return 0

    # 按 agent 聚合
    by_agent: Dict[str, List[Dict[str, Any]]] = {}
    for act in activities_payload:
        key = f"{act.get('agent_id')}|{act.get('agent_name')}"
        by_agent.setdefault(key, []).append(act)

    lines = [
        f"模拟 {simulation_id} 平台 {platform} 的行为信号摘要："
    ]
    for key, acts in by_agent.items():
        agent_id, agent_name = key.split('|', 1)
        persona_uuid = f"persona_{simulation_id}_{agent_id}"
        joined = ' | '.join(
            f"{a.get('action_type')}:{(a.get('text') or '')[:80]}"
            for a in acts
        )
        avg_sent = sum(_quick_sentiment(a.get('text') or '') for a in acts) / max(len(acts), 1)
        topics = []
        for a in acts:
            topics.extend(_extract_topic_keywords(a.get('text') or ''))
        # 去重保序
        seen = set()
        topics = [t for t in topics if not (t in seen or seen.add(t))][:5]

        lines.append(
            f"- SimulatedPersona {persona_uuid} (agent_id={agent_id}, name={agent_name}) "
            f"在第 {acts[0].get('round_num')} 轮的行为：{joined}"
        )
        lines.append(
            f"  情绪打分 sentiment={avg_sent:.2f}; "
            f"涉及话题 {', '.join(topics) if topics else '无'}; "
            f"行为数={len(acts)}"
        )
        lines.append(
            f"  → 追加到 SimulatedPersona {persona_uuid} 的 "
            f"sentiment_trajectory（值={avg_sent:.2f}）与 topic_switch_log。"
        )

    try:
        await graphiti.add_episode(
            name=f"BehaviorSignals {simulation_id} {platform} {datetime.now().isoformat()}",
            episode_body="\n".join(lines),
            source_description=f"OASIS simulation {simulation_id} 行为回写",
            reference_time=datetime.now(),
            group_id=simulation_id,
        )
        return len(activities_payload)
    except Exception as exc:
        logger.warning(f"写入行为信号失败: {exc}")
        return 0


def write_behavior_signals(
    activities: List[Any],
    simulation_id: Optional[str],
    platform: str,
) -> int:
    """
    将一批 AgentActivity 行为汇总写入画像图谱（双写 Zep + Graphiti）。
    
    Args:
        activities: AgentActivity 列表（duck-typed: 需要 agent_id/agent_name/action_type/
                    action_args/round_num/timestamp 属性）
        simulation_id: 模拟 ID；为空时跳过
        platform: 平台名 twitter/reddit
    
    Returns:
        成功处理的活动数；图谱未启用 / 失败时返回 0
    """
    if not simulation_id or not activities:
        return 0
    graphiti = get_graphiti()
    if graphiti is None:
        return 0

    payload: List[Dict[str, Any]] = []
    for a in activities:
        try:
            args = getattr(a, 'action_args', {}) or {}
            text = (
                args.get('content')
                or args.get('post_content')
                or args.get('original_content')
                or args.get('comment_content')
                or args.get('query')
                or ''
            )
            payload.append({
                'agent_id': getattr(a, 'agent_id', None),
                'agent_name': getattr(a, 'agent_name', ''),
                'action_type': getattr(a, 'action_type', ''),
                'round_num': getattr(a, 'round_num', 0),
                'timestamp': getattr(a, 'timestamp', ''),
                'text': text,
            })
        except Exception as exc:
            logger.debug(f"行为信号序列化跳过: {exc}")

    try:
        return run_async(_write_signals_async(graphiti, payload, simulation_id, platform))
    except Exception as exc:
        logger.warning(f"写行为信号失败: {exc}")
        return 0
