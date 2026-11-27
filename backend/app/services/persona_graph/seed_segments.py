"""
InvestorSegment 种子数据

将 CSOP 已有的 6 类客户画像作为 InvestorSegment 节点种子化写入画像图谱。
参考：execution_layer_design.md 中的客户分群定义。
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from ...utils.logger import get_logger
from .client import get_graphiti, run_async
from .schema import InvestorSegment

logger = get_logger('finrex.persona_graph.seed')


# CSOP 6 类客户画像种子数据
INVESTOR_SEGMENTS_SEED: List[InvestorSegment] = [
    InvestorSegment(
        segment_id='seg_aggressive',
        name='积极型',
        risk_appetite='high',
        description='追求高收益，风险承受力强，偏好成长股、科技股、高 Beta ETF',
        recommended_products=['科技 ETF', '成长股 ETF', '杠杆 ETF', '主题概念股'],
        talking_points=[
            '把握新兴产业 alpha',
            '聚焦人工智能、半导体、新能源主题',
            '高弹性的市场领涨标的',
        ],
    ),
    InvestorSegment(
        segment_id='seg_conservative',
        name='保守型',
        risk_appetite='low',
        description='风险厌恶，重视本金安全，偏好货币基金、短债 ETF、低波动产品',
        recommended_products=['货币市场 ETF', '短期国债 ETF', '低波蓝筹 ETF'],
        talking_points=[
            '本金安全是首要',
            '稳健年化 + 流动性兼顾',
            '波动可控，睡得着的资产',
        ],
    ),
    InvestorSegment(
        segment_id='seg_dividend',
        name='收息型',
        risk_appetite='mid',
        description='追求稳定现金流，偏好高股息 ETF、REITs、债券基金',
        recommended_products=['高股息 ETF', 'REITs', '亚洲高息 ETF', '公司债 ETF'],
        talking_points=[
            '月月分派，现金流可见',
            '股债平衡的稳健回报',
            '退休配置首选',
        ],
    ),
    InvestorSegment(
        segment_id='seg_short_term',
        name='短线交易型',
        risk_appetite='high',
        description='热衷波段交易，关注主题轮动与市场情绪',
        recommended_products=['行业主题 ETF', '杠杆/反向 ETF', '热点概念股'],
        talking_points=[
            '抓住市场热点轮动',
            'T+0 或灵活进出工具',
            '主题快速兑现',
        ],
    ),
    InvestorSegment(
        segment_id='seg_contrarian',
        name='逆向型',
        risk_appetite='mid',
        description='偏好低估值、左侧布局，关注被市场错杀的行业',
        recommended_products=['低估值蓝筹 ETF', '价值股 ETF', '左侧主题基金'],
        talking_points=[
            '估值修复机会',
            '人弃我取，等待回归',
            '反转主题左侧布局',
        ],
    ),
    InvestorSegment(
        segment_id='seg_global',
        name='全球配置型',
        risk_appetite='mid',
        description='重视分散，跨地区跨资产配置，偏好全球宽基与汇率对冲',
        recommended_products=['全球宽基 ETF', '美股核心 ETF', '新兴市场 ETF', '黄金 ETF'],
        talking_points=[
            '一篮子全球暴露',
            '降低单一市场系统性风险',
            '多元资产平衡',
        ],
    ),
]


async def _seed_async(graphiti, segments: List[InvestorSegment]) -> int:
    """异步写入种子数据"""
    count = 0
    now = datetime.now().isoformat()
    for seg in segments:
        # Graphiti 通过 add_episode 接收文本 + 自定义实体类型，会自动抽取
        # 但我们这里直接构造好 InvestorSegment 节点，需走文本通道让其识别
        text = (
            f"InvestorSegment 客户分群档案：\n"
            f"分群 ID: {seg.segment_id}\n"
            f"分群名称: {seg.name}\n"
            f"风险偏好: {seg.risk_appetite}\n"
            f"描述: {seg.description}\n"
            f"推荐产品: {', '.join(seg.recommended_products)}\n"
            f"销售话术: {' | '.join(seg.talking_points)}\n"
        )
        try:
            await graphiti.add_episode(
                name=f"InvestorSegment Seed - {seg.name}",
                episode_body=text,
                source_description='CSOP 客户画像种子数据',
                reference_time=datetime.now(),
                group_id='investor_segments',
            )
            count += 1
        except Exception as exc:
            logger.warning(f"种子分群 {seg.name} 写入失败: {exc}")
    return count


def seed_investor_segments() -> int:
    """
    将 6 类客户画像种子化写入 Graphiti。
    
    Returns:
        成功写入的分群数量；如未启用画像图谱则返回 0
    """
    graphiti = get_graphiti()
    if graphiti is None:
        logger.info("画像图谱未启用，跳过 InvestorSegment 种子化")
        return 0

    try:
        count = run_async(_seed_async(graphiti, INVESTOR_SEGMENTS_SEED))
        logger.info(f"已种子化 {count}/{len(INVESTOR_SEGMENTS_SEED)} 个 InvestorSegment")
        return count
    except Exception as exc:
        logger.warning(f"种子化失败: {exc}")
        return 0


if __name__ == '__main__':
    # 命令行调用：python -m backend.app.services.persona_graph.seed_segments
    seed_investor_segments()
