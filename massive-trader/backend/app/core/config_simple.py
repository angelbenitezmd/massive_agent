"""
Simplified configuration for Python 3.14 compatibility.

WATCHLIST CONFIGURATION
=======================
This config reads ticker lists from environment variables (.env file):

- WATCHLIST_TICKERS: Core "Best Stocks" universe
  High-quality, highly liquid S&P 100-style large caps.
  Sector-balanced for diversification.
  Used by: Scanner "Watchlist" tab, primary AI analysis.

- SCAN_UNIVERSE_TICKERS: Extended momentum universe
  Growth & momentum stocks for broader scanning.

- SPICY_TICKERS: High Volatility / "Spicy" list
  Meme stocks, high beta, story stocks.
  Used by: Scanner "High Volatility" tab.

All major US exchanges (NYSE, NASDAQ, AMEX) are supported.
No exchange-specific filtering is applied - Alpaca + Benzinga cover all.

TODO (future): Dynamic universe selection via nightly scoring/rotation.
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
        self.TRADING_MIN_SIGNAL_SCORE = float(os.getenv("TRADING_MIN_SIGNAL_SCORE", "50"))
        self.TRADING_FAST_MODE_URGENCY_THRESHOLD = float(os.getenv("TRADING_FAST_MODE_URGENCY_THRESHOLD", "0.8"))

        # WebSocket
        self.WS_ALLOWED_ORIGINS = os.getenv("WS_ALLOWED_ORIGINS", "*")
        self.WS_PORT = int(os.getenv("WS_PORT", "8001"))

        # Database
        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading_journal.db")

        # Logging
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE", "trading_system.log")

        # Watchlists
        self.WATCHLIST_TICKERS = os.getenv("WATCHLIST_TICKERS", "AAPL,MSFT,GOOGL")
        self.SCAN_UNIVERSE_TICKERS = os.getenv("SCAN_UNIVERSE_TICKERS", "")
        self.SPICY_TICKERS = os.getenv("SPICY_TICKERS", "")

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
    def universe(self) -> list:
        """Parse extended universe tickers into a list."""
        if not self.SCAN_UNIVERSE_TICKERS:
            return []
        return [ticker.strip() for ticker in self.SCAN_UNIVERSE_TICKERS.split(",") if ticker.strip()]

    @property
    def spicy(self) -> list:
        """Parse spicy high-vol tickers into a list."""
        if not self.SPICY_TICKERS:
            return []
        return [ticker.strip() for ticker in self.SPICY_TICKERS.split(",") if ticker.strip()]

    @property
    def is_paper_trading(self) -> bool:
        """Check if we're in paper trading mode."""
        return self.ALPACA_ENV != "live"


def get_settings() -> Settings:
    """Get settings instance."""
    return Settings()


# Create a global settings instance
settings = get_settings()