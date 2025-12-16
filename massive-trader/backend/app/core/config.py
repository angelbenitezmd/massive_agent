"""Configuration management using pydantic-settings."""
from typing import List, Literal, Optional
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import warnings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Benzinga / Massive API
    BENZINGA_BASE_URL: str = Field(default="https://api.massive.xyz")
    BENZINGA_API_KEY: str = Field(default="")

    # Alpaca Trading - CRITICAL: Default to paper trading
    ALPACA_API_KEY_ID: str = Field(default="")
    ALPACA_API_SECRET_KEY: str = Field(default="")
    ALPACA_ENV: Literal["paper", "live"] = Field(default="paper")

    # Alpaca URLs
    ALPACA_PAPER_BASE_URL: str = Field(default="https://paper-api.alpaca.markets")
    ALPACA_LIVE_BASE_URL: str = Field(default="https://api.alpaca.markets")
    ALPACA_DATA_BASE_URL: str = Field(default="https://data.alpaca.markets/v2")

    # AI / LLM
    ANTHROPIC_API_KEY: str = Field(default="")
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    AGENT_DESIGN_MODE: bool = Field(default=False, description="Enable design mode for agents (testing/development)")

    # Trading Engine
    TRADING_HYBRID_INTERVAL_SECONDS: int = Field(default=60)
    TRADING_DEFAULT_MAX_POSITION_RISK: float = Field(default=0.01)
    TRADING_DAILY_MAX_DRAWDOWN: float = Field(default=0.05)
    TRADING_MIN_SIGNAL_SCORE: float = Field(default=50.0)
    TRADING_FAST_MODE_URGENCY_THRESHOLD: float = Field(default=0.8)

    # WebSocket
    WS_ALLOWED_ORIGINS: str = Field(default="*")
    WS_PORT: int = Field(default=8001)

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./trading_journal.db")

    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="trading_system.log")

    # Watchlist & Ticker Lists
    WATCHLIST_TICKERS: str = Field(default="AAPL,MSFT,GOOGL,NVDA,AMZN,META,TSLA")
    SCAN_UNIVERSE_TICKERS: str = Field(default="")
    SPICY_TICKERS: str = Field(default="")
    HIGH_VOLUME_TICKERS: str = Field(default="")

    @property
    def alpaca_base_url(self) -> str:
        """Return the appropriate Alpaca base URL based on environment."""
        if self.ALPACA_ENV == "live":
            warnings.warn(
                "⚠️  LIVE TRADING MODE ENABLED - Real money at risk! ⚠️",
                UserWarning
            )
            return self.ALPACA_LIVE_BASE_URL
        return self.ALPACA_PAPER_BASE_URL

    @property
    def watchlist(self) -> List[str]:
        """Parse watchlist tickers into a list."""
        return [ticker.strip() for ticker in self.WATCHLIST_TICKERS.split(",") if ticker.strip()]

    @property
    def universe(self) -> List[str]:
        """Parse universe tickers into a list."""
        return [ticker.strip() for ticker in self.SCAN_UNIVERSE_TICKERS.split(",") if ticker.strip()]

    @property
    def spicy(self) -> List[str]:
        """Parse spicy/volatile tickers into a list."""
        return [ticker.strip() for ticker in self.SPICY_TICKERS.split(",") if ticker.strip()]

    @property
    def high_volume(self) -> List[str]:
        """Parse high volume tickers into a list."""
        return [ticker.strip() for ticker in self.HIGH_VOLUME_TICKERS.split(",") if ticker.strip()]

    @property
    def all_tickers(self) -> List[str]:
        """Return all unique tickers from all lists."""
        all_set = set(self.watchlist + self.universe + self.spicy + self.high_volume)
        return sorted(list(all_set))

    @property
    def is_paper_trading(self) -> bool:
        """Check if we're in paper trading mode."""
        return self.ALPACA_ENV != "live"

    @field_validator("ALPACA_ENV")
    def validate_alpaca_env(cls, v: str) -> str:
        """Validate and warn about trading environment."""
        if v == "live":
            print("\n" + "="*60)
            print("⚠️  WARNING: LIVE TRADING MODE CONFIGURED")
            print("Real money will be at risk!")
            print("Ensure you understand the risks before proceeding.")
            print("="*60 + "\n")
        else:
            print("\n✅ Paper trading mode enabled (safe mode)")
        return v

    @field_validator("TRADING_DEFAULT_MAX_POSITION_RISK", "TRADING_DAILY_MAX_DRAWDOWN")
    def validate_risk_percentages(cls, v: float) -> float:
        """Ensure risk percentages are reasonable."""
        if not 0 < v <= 1:
            raise ValueError(f"Risk value must be between 0 and 1, got {v}")
        return v

    def __repr__(self) -> str:
        """Safe representation without exposing secrets."""
        return (
            f"<Settings "
            f"env={self.ALPACA_ENV} "
            f"interval={self.TRADING_HYBRID_INTERVAL_SECONDS}s "
            f"max_risk={self.TRADING_DEFAULT_MAX_POSITION_RISK*100}%>"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Create a global settings instance
settings = get_settings()