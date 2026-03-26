from fastapi import APIRouter

from app.core.config import get_settings
from app.services.benzinga_simple import BenzingaClient

router = APIRouter()

settings = get_settings()


@router.get("/")
async def root():
  """Root endpoint."""
  # Note: benzinga connectivity is inferred from API key presence for this lightweight status.
  return {
    "message": "AI Trading System API",
    "version": "1.0.0",
    "benzinga_connected": bool(settings.BENZINGA_API_KEY),
    "docs": "/docs",
  }


@router.get("/health")
async def health_check():
  """Health check endpoint."""
  return {
    "status": "healthy",
    "environment": settings.ALPACA_ENV,
    "paper_trading": settings.is_paper_trading,
    "benzinga_connected": bool(settings.BENZINGA_API_KEY),
  }


@router.get("/status")
async def system_status():
  """Get system status and configuration."""
  return {
    "trading_env": settings.ALPACA_ENV,
    "is_paper": settings.is_paper_trading,
    "risk_settings": {
      "max_position_risk": settings.TRADING_DEFAULT_MAX_POSITION_RISK,
      "daily_max_drawdown": settings.TRADING_DAILY_MAX_DRAWDOWN,
      "min_signal_score": settings.TRADING_MIN_SIGNAL_SCORE,
    },
    "watchlist": settings.watchlist,
    "hybrid_interval": settings.TRADING_HYBRID_INTERVAL_SECONDS,
    "api_keys_configured": {
      "benzinga": bool(settings.BENZINGA_API_KEY),
      "alpaca": bool(settings.ALPACA_API_KEY_ID and settings.ALPACA_API_SECRET_KEY),
      "anthropic": bool(settings.ANTHROPIC_API_KEY),
    },
  }

