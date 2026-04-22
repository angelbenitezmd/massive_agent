"""
Simplified configuration for Python 3.14 compatibility.

Reads WATCHLIST_TICKERS from .env — one consolidated list of all tickers.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Simple settings class without pydantic-settings."""

    def __init__(self):
        # Benzinga / Massive API
        self.BENZINGA_BASE_URL = os.getenv("BENZINGA_BASE_URL", "https://api.massive.xyz")
        self.BENZINGA_API_KEY = os.getenv("BENZINGA_API_KEY", "")

        # Alpaca Trading
        self.ALPACA_API_KEY_ID = os.getenv("ALPACA_API_KEY_ID", "")
        self.ALPACA_API_SECRET_KEY = os.getenv("ALPACA_API_SECRET_KEY", "")
        self.ALPACA_ENV = os.getenv("ALPACA_ENV", "paper")

        # Alpaca URLs
        self.ALPACA_PAPER_BASE_URL = os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")
        self.ALPACA_LIVE_BASE_URL = os.getenv("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets")
        self.ALPACA_DATA_BASE_URL = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets/v2")

        # AI / LLM
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

        # Trading Engine
        self.TRADING_HYBRID_INTERVAL_SECONDS = int(os.getenv("TRADING_HYBRID_INTERVAL_SECONDS", "60"))
        self.TRADING_DEFAULT_MAX_POSITION_RISK = float(os.getenv("TRADING_DEFAULT_MAX_POSITION_RISK", "0.01"))
        self.TRADING_DAILY_MAX_DRAWDOWN = float(os.getenv("TRADING_DAILY_MAX_DRAWDOWN", "0.05"))
        self.TRADING_MIN_SIGNAL_SCORE = float(os.getenv("TRADING_MIN_SIGNAL_SCORE", "70"))
        self.TRADING_SCAN_BUY_SCORE = float(os.getenv("TRADING_SCAN_BUY_SCORE", "70"))
        self.TRADING_LLM_RESCORE_MIN_SCORE = float(os.getenv("TRADING_LLM_RESCORE_MIN_SCORE", "60"))
        self.TRADING_ELITE_SIGNAL_SCORE = float(os.getenv("TRADING_ELITE_SIGNAL_SCORE", "80"))
        self.TRADING_FAST_MODE_URGENCY_THRESHOLD = float(os.getenv("TRADING_FAST_MODE_URGENCY_THRESHOLD", "0.8"))

        # WebSocket
        self.WS_ALLOWED_ORIGINS = os.getenv("WS_ALLOWED_ORIGINS", "*")
        self.WS_PORT = int(os.getenv("WS_PORT", "8001"))

        # Database
        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading_journal.db")

        # Logging
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE", "trading_system.log")

        # Watchlist
        self.WATCHLIST_TICKERS = os.getenv("WATCHLIST_TICKERS", "AAPL,MSFT,GOOGL")

        # Print trading mode
        if self.ALPACA_ENV == "live":
            print("\n" + "="*60)
            print("⚠️  WARNING: LIVE TRADING MODE CONFIGURED")
            print("Real money will be at risk!")
            print("="*60 + "\n")
        else:
            print("\n✅ Paper trading mode enabled (safe mode)")

    @property
    def alpaca_base_url(self) -> str:
        """Return the appropriate Alpaca base URL based on environment."""
        if self.ALPACA_ENV == "live":
            return self.ALPACA_LIVE_BASE_URL
        return self.ALPACA_PAPER_BASE_URL

    @property
    def watchlist(self) -> list:
        """Parse watchlist tickers into a list."""
        return [ticker.strip() for ticker in self.WATCHLIST_TICKERS.split(",") if ticker.strip()]

    @property
    def all_tickers(self) -> list:
        """Get all unique tickers (same as watchlist now)."""
        return self.watchlist

    @property
    def is_paper_trading(self) -> bool:
        """Check if we're in paper trading mode."""
        return self.ALPACA_ENV != "live"


def get_settings() -> Settings:
    """Get settings instance."""
    return Settings()


# Create a global settings instance
settings = get_settings()