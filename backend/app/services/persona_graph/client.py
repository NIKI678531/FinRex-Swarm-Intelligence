"""
Graphiti 客户端封装

提供单例 Graphiti 实例，未配置或依赖缺失时优雅降级（返回 None），
确保画像图谱失败不影响主模拟流程。
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from ...config import Config
from ...utils.logger import get_logger

logger = get_logger('finrex.persona_graph.client')

_graphiti_instance: Optional[object] = None
_graphiti_lock = threading.Lock()
_init_failed = False


def is_persona_graph_enabled() -> bool:
    """画像图谱是否启用（配置开关 + URI 已设置）"""
    if not getattr(Config, 'GRAPHITI_ENABLED', False):
        return False
    if not Config.GRAPHITI_URI:
        return False
    return True


def get_graphiti():
    """
    获取 Graphiti 单例。
    
    Returns:
        Graphiti 实例；如果未启用 / 依赖缺失 / 初始化失败 则返回 None
    """
    global _graphiti_instance, _init_failed

    if not is_persona_graph_enabled():
        return None

    if _init_failed:
        return None

    if _graphiti_instance is not None:
        return _graphiti_instance

    with _graphiti_lock:
        if _graphiti_instance is not None:
            return _graphiti_instance
        if _init_failed:
            return None

        try:
            backend = (Config.GRAPHITI_BACKEND or 'falkordb').lower()
            uri = Config.GRAPHITI_URI
            user = Config.GRAPHITI_USER or None
            password = Config.GRAPHITI_PASSWORD or None

            if backend == 'falkordb':
                # FalkorDB driver
                from graphiti_core import Graphiti
                from graphiti_core.driver.falkordb_driver import FalkorDriver

                # 解析 URI 形如 falkor://localhost:6379 或 redis://localhost:6379
                # FalkorDriver 接收 host, port, password
                host, port = _parse_falkor_uri(uri)
                driver = FalkorDriver(host=host, port=port, password=password)
                _graphiti_instance = Graphiti(
                    graph_driver=driver,
                )
            elif backend == 'neo4j':
                from graphiti_core import Graphiti
                _graphiti_instance = Graphiti(
                    uri=uri,
                    user=user or 'neo4j',
                    password=password or 'password',
                )
            else:
                logger.warning(f"未知的 Graphiti 后端: {backend}")
                _init_failed = True
                return None

            logger.info(
                f"Graphiti 初始化成功: backend={backend}, uri={uri}"
            )

            # 异步建索引（非阻塞主进程）
            try:
                asyncio.run(_graphiti_instance.build_indices_and_constraints())
            except RuntimeError:
                # 已在 event loop 内（被 Flask 调用），用 ensure_future
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        _graphiti_instance.build_indices_and_constraints()
                    )
                finally:
                    loop.close()
            except Exception as exc:
                logger.warning(f"Graphiti 索引建立失败（可忽略）: {exc}")

            return _graphiti_instance

        except ImportError as exc:
            logger.warning(
                f"graphiti-core 未安装，画像图谱降级为 no-op: {exc}"
            )
            _init_failed = True
            return None
        except Exception as exc:
            logger.warning(
                f"Graphiti 初始化失败，画像图谱降级为 no-op: {exc}"
            )
            _init_failed = True
            return None


def close_graphiti():
    """关闭 Graphiti 连接"""
    global _graphiti_instance
    if _graphiti_instance is None:
        return
    try:
        close = getattr(_graphiti_instance, 'close', None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(result)
                finally:
                    loop.close()
    except Exception as exc:
        logger.debug(f"关闭 Graphiti 时异常: {exc}")
    finally:
        _graphiti_instance = None


def _parse_falkor_uri(uri: str) -> tuple[str, int]:
    """解析 falkor://host:port 或 redis://host:port 形式 URI"""
    s = uri
    for prefix in ('falkor://', 'redis://', 'falkordb://'):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if '/' in s:
        s = s.split('/', 1)[0]
    if ':' in s:
        host, port_str = s.rsplit(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            port = 6379
    else:
        host, port = s, 6379
    return host or 'localhost', port


def run_async(coro):
    """工具函数：在同步上下文运行 async 协程"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已在事件循环里，建一个新 loop 跑
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        return loop.run_until_complete(coro)
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
