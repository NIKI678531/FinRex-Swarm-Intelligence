"""金融预测报告（OIF Strategy）相关服务。

包含：
- market_provider: 行情数据 provider（包装现有 MarketDataService）
- news_provider: 实时新闻 provider（FMP/RSS + Step1 用户评论）
- sentiment_provider: 情绪打分（HF FinBERT + VADER fallback）
- financial_forecast_analyzer: 聚合输出 Observed / Inferred / Simulated / Forecast
"""

from .market_provider import MarketProvider
from .news_provider import NewsProvider
from .sentiment_provider import SentimentProvider
from .financial_forecast_analyzer import FinancialForecastAnalyzer
from .crypto_forecast_service import CryptoForecastService
from .crypto_market_provider import CryptoMarketProvider
from .stock_forecast_service import StockForecastService
from .yfinance_news_provider import YFinanceNewsProvider
from .reddit_provider import RedditProvider
from .stocktwits_provider import StockTwitsProvider

__all__ = [
    "MarketProvider",
    "NewsProvider",
    "SentimentProvider",
    "FinancialForecastAnalyzer",
    "CryptoForecastService",
    "CryptoMarketProvider",
    "StockForecastService",
    "YFinanceNewsProvider",
    "RedditProvider",
    "StockTwitsProvider",
]
