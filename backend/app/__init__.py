"""
FinRex Backend - Flask应用工厂
"""

import os
import warnings

# 抑制 multiprocessing resource_tracker 的警告（来自第三方库如 transformers）
# 需要在所有其他导入之前设置
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 设置JSON编码：确保中文直接显示（而不是 \uXXXX 格式）
    # Flask >= 2.3 使用 app.json.ensure_ascii，旧版本使用 JSON_AS_ASCII 配置
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # 设置日志
    logger = setup_logger('finrex')
    
    # 只在 reloader 子进程中打印启动信息（避免 debug 模式下打印两次）
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("FinRex Backend 启动中...")
        logger.info("=" * 50)
    
    # 启用CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # 注册模拟进程清理函数（确保服务器关闭时终止所有模拟进程）
    try:
        from .services.simulation_runner import SimulationRunner
        SimulationRunner.register_cleanup()
        if should_log_startup:
            logger.info("已注册模拟进程清理函数")
    except Exception as exc:  # 缺少仿真依赖时降级
        if should_log_startup:
            logger.warning(f"未启用仿真进程清理（依赖缺失）：{exc}")
    
    # 请求日志中间件
    @app.before_request
    def log_request():
        logger = get_logger('finrex.request')
        logger.debug(f"请求: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"请求体: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('finrex.request')
        logger.debug(f"响应: {response.status_code}")
        return response
    
    # 注册蓝图
    from .controllers import graph_bp, simulation_bp, report_bp, public_opinion_bp, content_studio_bp, financial_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(public_opinion_bp, url_prefix='/api/public-opinion')
    app.register_blueprint(content_studio_bp, url_prefix='/api/content-studio')
    app.register_blueprint(financial_bp, url_prefix='/api/financial')

    # 画像图谱蓝图（可选；缺依赖时不阻塞启动）
    try:
        from .controllers.persona import persona_bp
        app.register_blueprint(persona_bp, url_prefix='/api/persona')
        if should_log_startup:
            logger.info("已注册画像图谱 API: /api/persona/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册画像图谱 API（依赖缺失）: {exc}")
    
    # 健康检查
    try:
        from .controllers.reaction import reaction_bp
        app.register_blueprint(reaction_bp, url_prefix='/api/reaction')
        if should_log_startup:
            logger.info("Registered reaction analysis API: /api/reaction/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"Reaction analysis API not registered: {exc}")

    # 资产配置 / ETF 量化预测蓝图（可选；缺 yfinance/pyyaml 时降级跳过）
    try:
        from .controllers.asset_allocation import asset_allocation_bp
        app.register_blueprint(asset_allocation_bp, url_prefix='/api')
        if should_log_startup:
            logger.info("已注册资产配置 API: /api/report/<id>/asset-allocation, /api/asset-allocation/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册资产配置 API（依赖缺失）: {exc}")

    # Weekly bins-based Validation Lab
    try:
        from .controllers.validation import validation_bp
        app.register_blueprint(validation_bp, url_prefix='/api/validation')
        if should_log_startup:
            logger.info("已注册 Weekly Validation Lab API: /api/validation/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 Weekly Validation Lab API: {exc}")

    # Shared BTC market data API (Binance public REST, read-only)
    try:
        from .controllers.market import market_bp
        app.register_blueprint(market_bp, url_prefix='/api/market')
        if should_log_startup:
            logger.info("已注册 BTC Market Data API: /api/market/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 BTC Market Data API: {exc}")

    # Quant subsystem (strategy backtest + paper-trading signals) — lazy heavy deps
    try:
        from .controllers.quant import quant_bp
        app.register_blueprint(quant_bp, url_prefix='/api/quant')
        if should_log_startup:
            logger.info("已注册 Quant Hybrid Alpha API: /api/quant/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 Quant Hybrid Alpha API: {exc}")

    # Multi-asset paper trading
    try:
        from .controllers.paper_trading import paper_trading_bp
        app.register_blueprint(paper_trading_bp, url_prefix='/api/paper-trading')
        if should_log_startup:
            logger.info("已注册 Multi-asset Paper Trading API: /api/paper-trading/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 Multi-asset Paper Trading API: {exc}")

    # FMP News & Social Sentiment unified API (covers all 15 stable endpoints)
    try:
        from .controllers.fmp_news import fmp_news_bp
        app.register_blueprint(fmp_news_bp, url_prefix='/api/fmp/news')
        if should_log_startup:
            logger.info("已注册 FMP News API: /api/fmp/news/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 FMP News API: {exc}")

    # Stock sentiment seed sources (Phase A: yfinance / reddit / stocktwits)
    try:
        from .controllers.yfinance_news import yfinance_news_bp
        app.register_blueprint(yfinance_news_bp, url_prefix='/api/yfinance')
        if should_log_startup:
            logger.info("已注册 YFinance News API: /api/yfinance/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 YFinance News API: {exc}")
    try:
        from .controllers.reddit_news import reddit_news_bp
        app.register_blueprint(reddit_news_bp, url_prefix='/api/reddit')
        if should_log_startup:
            logger.info("已注册 Reddit News API: /api/reddit/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 Reddit News API: {exc}")
    try:
        from .controllers.stocktwits import stocktwits_bp
        app.register_blueprint(stocktwits_bp, url_prefix='/api/stocktwits')
        if should_log_startup:
            logger.info("已注册 StockTwits API: /api/stocktwits/*")
    except Exception as exc:
        if should_log_startup:
            logger.warning(f"未注册 StockTwits API: {exc}")


    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'FinRex Backend'}

    # Foundation models warmup (Kronos + Chronos-Bolt). Non-blocking: log only.
    # Surfaces real load errors (missing torch / einops / HF download) at startup
    # instead of letting predict_ensemble silently fall back per-request.
    if should_log_startup:
        try:
            from .quant.models.foundation_ensemble import get_foundation_status
            fstatus = get_foundation_status(load=True, run_smoke=False)
            if fstatus.get("available"):
                logger.info(
                    "Foundation models ready (%s): kronos=%s chronos=%s",
                    fstatus.get("ensemble"),
                    fstatus.get("kronos", {}).get("available"),
                    fstatus.get("chronos", {}).get("available"),
                )
            else:
                logger.error(
                    "Foundation models UNAVAILABLE — predictions will fall back to range midpoint. "
                    "kronos_error=%s | chronos_error=%s",
                    (fstatus.get("kronos") or {}).get("last_error"),
                    (fstatus.get("chronos") or {}).get("last_error"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Foundation warmup skipped: %s", exc)

    if should_log_startup:
        logger.info("FinRex Backend 启动完成")
    
    return app
