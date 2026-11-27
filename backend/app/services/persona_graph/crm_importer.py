"""
CRM Importer - 真实 CRM 数据接入占位

提供 CSV/JSON 导入接口，将真实客户数据写入 Graphiti 作为 RealClient 节点，
并通过特征匹配 / LLM 写 MATCHES 边到对应 InvestorSegment。

注意：当前为占位实现，真实 CRM 接入需补全字段映射与脱敏逻辑。
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from .client import get_graphiti, run_async
from .schema import RealClient

logger = get_logger('finrex.persona_graph.crm')


async def _write_clients_async(graphiti, clients: List[RealClient]) -> int:
    written = 0
    for c in clients:
        text = (
            f"RealClient 真实客户档案：\n"
            f"客户 ID: {c.client_id}\n"
            f"画像描述: {c.anonymized_profile}\n"
            f"当前持仓: {', '.join(c.current_holdings)}\n"
        )
        try:
            await graphiti.add_episode(
                name=f"RealClient {c.client_id}",
                episode_body=text,
                source_description='CRM import',
                reference_time=datetime.now(),
                group_id='real_clients',
            )
            written += 1
        except Exception as exc:
            logger.warning(f"写入 RealClient {c.client_id} 失败: {exc}")
    return written


def import_clients(clients: List[RealClient]) -> int:
    """直接传入 RealClient 列表批量导入"""
    graphiti = get_graphiti()
    if graphiti is None:
        logger.info("画像图谱未启用，跳过 CRM 导入")
        return 0
    try:
        return run_async(_write_clients_async(graphiti, clients))
    except Exception as exc:
        logger.warning(f"批量导入失败: {exc}")
        return 0


def import_from_csv(file_path: str) -> int:
    """
    从 CSV 文件导入。
    
    CSV 需含列：client_id, anonymized_profile, current_holdings (分号分隔)
    """
    if not os.path.exists(file_path):
        logger.warning(f"CSV 文件不存在: {file_path}")
        return 0
    clients: List[RealClient] = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            holdings_raw = row.get('current_holdings') or ''
            holdings = [h.strip() for h in holdings_raw.split(';') if h.strip()]
            clients.append(RealClient(
                client_id=row.get('client_id'),
                anonymized_profile=row.get('anonymized_profile'),
                current_holdings=holdings,
            ))
    return import_clients(clients)


def import_from_json(file_path: str) -> int:
    """
    从 JSON 文件导入。
    
    JSON 结构：[{"client_id": ..., "anonymized_profile": ..., "current_holdings": [...]}, ...]
    """
    if not os.path.exists(file_path):
        logger.warning(f"JSON 文件不存在: {file_path}")
        return 0
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        logger.warning("JSON 顶层应为数组")
        return 0
    clients = [RealClient(**item) for item in data if isinstance(item, dict)]
    return import_clients(clients)
