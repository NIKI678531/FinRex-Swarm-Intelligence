"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: FinRex/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'finrex-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    LLM_DEPLOYMENT_NAME = os.environ.get('LLM_DEPLOYMENT_NAME')
    STOCK_TECH_LLM_ENABLED = os.environ.get('STOCK_TECH_LLM_ENABLED', 'false').lower() == 'true'
    STOCK_TECH_LLM_MODEL = os.environ.get('STOCK_TECH_LLM_MODEL', '')
    STOCK_TECH_LLM_CACHE_TTL_SECONDS = int(os.environ.get('STOCK_TECH_LLM_CACHE_TTL_SECONDS', '21600'))
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    # Zep episode 单次构建上限（避免一次跑爆账号配额）。0 = 不限制。
    ZEP_MAX_EPISODES_PER_BUILD = int(os.environ.get('ZEP_MAX_EPISODES_PER_BUILD', '40'))

    # ===== Persona Graph (Graphiti) =====
    # 用户画像图谱后端配置；未设置时自动降级，主流程不受影响
    # 默认连本地 docker-compose 启动的 FalkorDB
    GRAPHITI_ENABLED = os.environ.get('GRAPHITI_ENABLED', 'true').lower() == 'true'
    GRAPHITI_BACKEND = os.environ.get('GRAPHITI_BACKEND', 'falkordb')  # falkordb | neo4j
    GRAPHITI_URI = os.environ.get('GRAPHITI_URI', 'falkor://localhost:6379')
    GRAPHITI_USER = os.environ.get('GRAPHITI_USER', '')
    GRAPHITI_PASSWORD = os.environ.get('GRAPHITI_PASSWORD', '')
    GRAPHITI_DATABASE = os.environ.get('GRAPHITI_DATABASE', 'finrex_persona')

    # Financial Modeling Prep (现实种子文章 API) 配置
    FMP_API_KEY = os.environ.get('FMP_API_KEY')
    FMP_BASE_URL = os.environ.get('FMP_BASE_URL', 'https://financialmodelingprep.com/stable')

    # Hugging Face remote inference (optional public-opinion enrichment)
    HF_TOKEN = os.environ.get('HF_TOKEN')
    HF_ENABLE_REMOTE_INFERENCE = os.environ.get('HF_ENABLE_REMOTE_INFERENCE', 'true').lower() != 'false'
    HF_INFERENCE_BASE_URL = os.environ.get(
        'HF_INFERENCE_BASE_URL',
        'https://router.huggingface.co/hf-inference/models'
    )
    HF_FINANCIAL_SENTIMENT_MODEL = os.environ.get(
        'HF_FINANCIAL_SENTIMENT_MODEL',
        'mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis'
    )
    HF_EMOTION_MODEL = os.environ.get(
        'HF_EMOTION_MODEL',
        'tabularisai/multilingual-emotion-classification'
    )
    # tabularisai/multilingual-emotion-classification is CC-BY-NC-4.0.
    # Keep remote emotion inference behind an explicit guard; local rules still run.
    HF_ALLOW_NON_COMMERCIAL_MODELS = os.environ.get('HF_ALLOW_NON_COMMERCIAL_MODELS', 'false').lower() == 'true'
    HF_TIMEOUT_SECONDS = int(os.environ.get('HF_TIMEOUT_SECONDS', '8'))
    HF_MAX_ITEMS_PER_REQUEST = int(os.environ.get('HF_MAX_ITEMS_PER_REQUEST', '12'))

    # Cloudflare D1 (Binance 评论区数据源)
    # 表 posts 里包含 Binance Square 等社区抓取的帖子/评论
    CLOUDFLARE_D1_ACCOUNT_ID = os.environ.get(
        'CLOUDFLARE_D1_ACCOUNT_ID',
        ''
    )
    CLOUDFLARE_D1_DATABASE_ID = os.environ.get(
        'CLOUDFLARE_D1_DATABASE_ID',
        ''
    )
    CLOUDFLARE_D1_API_TOKEN = os.environ.get(
        'CLOUDFLARE_D1_API_TOKEN',
        ''
    )
    # Binance D1 中 posts.source 的合法取值（限制以防 SQL 注入阶性 + 静默过滤）
    BINANCE_D1_ALLOWED_SOURCES = ['feed', 'hashtag', 'news', 'user']
    # 默认拉取哪个 source；空字符串表示不过滤（返回所有）
    BINANCE_D1_DEFAULT_SOURCE = os.environ.get('BINANCE_D1_DEFAULT_SOURCE', 'news')
    # 单次最大返回条数（控制响应体大小，避免拉爆）
    BINANCE_D1_MAX_LIMIT = int(os.environ.get('BINANCE_D1_MAX_LIMIT', '50'))
    # 单条 content 最大字符数（前端列表预览，避免一次返回过大）
    BINANCE_D1_CONTENT_MAX_CHARS = int(
        os.environ.get('BINANCE_D1_CONTENT_MAX_CHARS', '4000')
    )
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # ===== Polymarket (read-only public API) + validation calibration =====
    # Used purely as a market-calibration benchmark for our internal forecasts.
    # No wallets, no signing, no orders are ever placed against Polymarket.
    POLYMARKET_GAMMA_BASE = os.environ.get(
        'POLYMARKET_GAMMA_BASE', 'https://gamma-api.polymarket.com'
    )
    POLYMARKET_CLOB_BASE = os.environ.get(
        'POLYMARKET_CLOB_BASE', 'https://clob.polymarket.com'
    )
    POLYMARKET_CACHE_TTL = int(os.environ.get('POLYMARKET_CACHE_TTL', '600'))

    # Weekly validation engine. Legacy env fallbacks keep existing local
    # .env files and databases working while code uses validation names.
    VALIDATION_INITIAL_CAPITAL = float(
        os.environ.get('VALIDATION_INITIAL_CAPITAL', os.environ.get('PAPER_TRADE_INITIAL_CAPITAL', '10000'))
    )
    VALIDATION_DB_URL = os.environ.get(
        'VALIDATION_DB_URL',
        os.environ.get(
            'PAPER_TRADE_DB_URL',
            'sqlite:///' + os.path.join(os.path.dirname(__file__), '../uploads/paper_trade.db'),
        ),
    )

    # Weekly validation desk — edge gates & cost model
    VALIDATION_MIN_EDGE = float(os.environ.get('VALIDATION_MIN_EDGE', '0.03'))
    VALIDATION_MAX_POSITION_PCT = float(
        os.environ.get('VALIDATION_MAX_POSITION_PCT', os.environ.get('PAPER_TRADE_MAX_POSITION_PCT', '0.05'))
    )
    VALIDATION_POLY_FEE_PCT = float(os.environ.get('VALIDATION_POLY_FEE_PCT', '0.0'))
    VALIDATION_POLY_HALF_SPREAD_PCT = float(
        os.environ.get('VALIDATION_POLY_HALF_SPREAD_PCT', '0.01')
    )
    VALIDATION_DEFAULT_MODEL = os.environ.get(
        'VALIDATION_DEFAULT_MODEL', 'price_point_calibrated_ml'
    )

    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY 未配置")
        return errors
