"""HTTP controller layer."""

import logging

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
public_opinion_bp = Blueprint('public_opinion', __name__)
content_studio_bp = Blueprint('content_studio', __name__)
financial_bp = Blueprint('financial', __name__)

# persona_bp 在 .persona 子模块中定义并直接导出
# 这里不预先创建空 Blueprint，避免与子模块定义冲突
_logger = logging.getLogger('finrex.controllers.bootstrap')


def _safe_import(module_name: str) -> None:
    """尝试导入子模块，失败时降级为警告。

    用于让执行层等轻量蓝图在缺少 LLM/仿真依赖时仍可挂载。
    """
    try:
        __import__(f"{__name__}.{module_name}", fromlist=['_'])
    except Exception as exc:  # pragma: no cover - depends on optional deps
        _logger.warning("跳过加载 %s 蓝图（缺少依赖）: %s", module_name, exc)


for _module in ('graph', 'articles', 'simulation', 'report', 'public_opinion', 'content_studio', 'persona', 'reaction', 'financial'):
    _safe_import(_module)

