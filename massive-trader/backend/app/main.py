"""Simplified FastAPI application with real Benzinga integration."""
import logging
import asyncio
import random
import json
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os

# Use simple config
from app.core.config_simple import get_settings
from app.services.benzinga_simple import BenzingaClient
from app.services.alpaca_trader import alpaca_trader
from app.services.dashboard_service import DashboardService
from app.services.position_manager import PositionManager, init_position_manager, get_position_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Benzinga client
benzinga_client = None

# Simple TTL cache for data (reduces API calls while staying fresh)
_sentiment_cache = {}
_momentum_cache = {}
_scan_cache = {}
SENTIMENT_CACHE_TTL = 30   # Cache sentiment for 30 seconds
MOMENTUM_CACHE_TTL = 15    # Cache momentum for 15 seconds (price-sensitive)
SCAN_CACHE_TTL = 20        # Cache scan results for 20 seconds

# Position sizing defaults
DEFAULT_RISK_PER_TRADE = 0.025  # 2.5% of portfolio per trade
# Dynamic max position based on signal score (higher score = more conviction = larger position allowed)
MAX_POSITION_PCT_BASE = 0.12      # 12% max for standard signals (score 70-79)
MAX_POSITION_PCT_GOOD = 0.22      # 22% max for good signals (score 80-89)
MAX_POSITION_PCT_EXCELLENT = 0.28  # 28% max for excellent signals (score 90+)
MIN_SHARES = 1
MAX_SHARES = 500  # Safety cap
MIN_POSITION_VALUE = 300  # Minimum $300 position to make trades meaningful
TARGET_POSITION_PCT_HIGH_CONF = 0.12  # Target 12% position for high confidence (>0.8)
TARGET_POSITION_PCT_MED_CONF = 0.07  # Target 7% position for medium confidence (0.6-0.8)
TARGET_POSITION_PCT_LOW_CONF = 0.03  # Target 3% position for low confidence (<0.6)


def calculate_position_size(
    price: float,
    stop_loss_price: float,
    confidence: float = 0.7,
    risk_pct: float = DEFAULT_RISK_PER_TRADE,
    signal_score: int = 70
) -> int:
    """
    Calculate position size using a hybrid approach:
    1. Risk-based sizing (how much we can lose)
    2. Target position sizing (based on confidence/signal strength)
    3. Take the larger of the two (within constraints) to maximize opportunity

    Formula considers:
        - Account equity and buying power
        - Stop loss distance (risk per share)
        - Signal confidence (scales position aggressively)
        - Signal score (bonus for high-conviction trades)
        - Minimum position value (avoid tiny meaningless trades)

    Args:
        price: Entry price per share
        stop_loss_price: Stop loss price
        confidence: Signal confidence (0-1), scales position size
        risk_pct: Percentage of portfolio to risk per trade
        signal_score: Combined signal score (0-100)

    Returns:
        Number of shares to buy (integer)
    """
    try:
        # Get account info
        account = alpaca_trader.get_account_status()
        if not account:
            logger.warning("Could not get account status, using default 15 shares")
            return 15

        equity = float(account.get("equity", 100000))
        buying_power = float(account.get("buying_power", equity))

        if price <= 0:
            return MIN_SHARES

        # === METHOD 1: Risk-based sizing ===
        risk_per_share = abs(price - stop_loss_price)
        if risk_per_share < 0.01:
            risk_per_share = price * 0.02  # Default 2% stop

        # Aggressive confidence scaling: 0.4 to 1.3 range
        # High confidence (0.85+) gets a bonus multiplier
        if confidence >= 0.85:
            confidence_multiplier = 1.0 + (confidence - 0.85) * 2  # 1.0 to 1.3
        elif confidence >= 0.6:
            confidence_multiplier = 0.6 + (confidence - 0.6) * 1.6  # 0.6 to 1.0
        else:
            confidence_multiplier = 0.4 + (confidence * 0.33)  # 0.4 to 0.6

        # Aggressive bonus for high signal scores
        if signal_score >= 90:
            score_bonus = 1.75 + (signal_score - 90) * 0.025  # 1.75x at 90, up to 2.0x at 100
        elif signal_score >= 80:
            score_bonus = 1.2 + (signal_score - 80) * 0.055   # 1.2x at 80, up to 1.75x at 90
        else:
            score_bonus = 1.0 + max(0, (signal_score - 70) * 0.02)  # 1.0x at 70, up to 1.2x at 80

        risk_amount = equity * risk_pct * confidence_multiplier * score_bonus
        shares_from_risk = int(risk_amount / risk_per_share)

        # === METHOD 2: Target position sizing ===
        # Determine target position % based on confidence
        if confidence >= 0.8:
            target_pct = TARGET_POSITION_PCT_HIGH_CONF
        elif confidence >= 0.6:
            target_pct = TARGET_POSITION_PCT_MED_CONF
        else:
            target_pct = TARGET_POSITION_PCT_LOW_CONF

        # Apply score bonus to target
        target_position_value = equity * target_pct * score_bonus
        shares_from_target = int(target_position_value / price)

        # === METHOD 3: Minimum position value ===
        # Ensure we don't make tiny trades that aren't worth the commission/spread
        min_shares_for_value = int(MIN_POSITION_VALUE / price)

        # === COMBINE: Take the LARGER of risk-based and target-based ===
        # This maximizes opportunity while respecting constraints
        shares_base = max(shares_from_risk, shares_from_target, min_shares_for_value)

        # === Apply constraints ===
        # Dynamic max position size based on signal score (higher score = more conviction)
        if signal_score >= 90:
            max_position_pct = MAX_POSITION_PCT_EXCELLENT  # 20% for exceptional signals
        elif signal_score >= 80:
            max_position_pct = MAX_POSITION_PCT_GOOD  # 15% for good signals
        else:
            max_position_pct = MAX_POSITION_PCT_BASE  # 12% for standard signals

        max_position_value = equity * max_position_pct
        shares_from_max_position = int(max_position_value / price)

        # Buying power constraint (use up to 60% of buying power per trade)
        shares_from_buying_power = int(buying_power * 0.6 / price)

        # Final calculation: minimum of (base, constraints), but at least MIN_SHARES
        shares = min(shares_base, shares_from_max_position, shares_from_buying_power, MAX_SHARES)
        shares = max(shares, MIN_SHARES)

        # Calculate final position value for logging
        position_value = shares * price
        position_pct = (position_value / equity) * 100

        logger.info(
            f"Position sizing: equity=${equity:,.0f}, price=${price:.2f}, "
            f"conf={confidence:.2f}, score={signal_score}, max_pct={max_position_pct*100:.0f}%, "
            f"risk_shares={shares_from_risk}, target_shares={shares_from_target}, "
            f"min_value_shares={min_shares_for_value} -> {shares} shares "
            f"(${position_value:,.0f}, {position_pct:.1f}% of portfolio)"
        )

        return shares

    except Exception as e:
        logger.error(f"Position sizing error: {e}, defaulting to 15 shares")
        return 15

# Auto-trade state (persisted to file for restarts)
AUTO_TRADE_STATE_FILE = Path(__file__).parent.parent / "data" / "auto_trade_state.json"
_auto_trade_enabled = False
_auto_trade_interval = 60  # seconds between trade scans

def load_auto_trade_state():
    """Load auto-trade state from disk."""
    global _auto_trade_enabled, _auto_trade_interval
    try:
        if AUTO_TRADE_STATE_FILE.exists():
            with open(AUTO_TRADE_STATE_FILE, "r") as f:
                state = json.load(f)
                _auto_trade_enabled = state.get("enabled", False)
                _auto_trade_interval = state.get("interval", 60)
                logger.info(f"Loaded auto-trade state: enabled={_auto_trade_enabled}, interval={_auto_trade_interval}s")
    except Exception as e:
        logger.error(f"Failed to load auto-trade state: {e}")

def save_auto_trade_state():
    """Save auto-trade state to disk."""
    try:
        AUTO_TRADE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTO_TRADE_STATE_FILE, "w") as f:
            json.dump({
                "enabled": _auto_trade_enabled,
                "interval": _auto_trade_interval,
                "updated_at": datetime.utcnow().isoformat()
            }, f)
    except Exception as e:
        logger.error(f"Failed to save auto-trade state: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    global benzinga_client
    settings = get_settings()

    logger.info("="*60)
    logger.info("AI Trading System Starting (With Benzinga Integration)")
    logger.info(f"Trading Environment: {settings.ALPACA_ENV.upper()}")

    if settings.ALPACA_ENV == "live":
        logger.warning("⚠️ LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
    else:
        logger.info("✅ Paper trading mode (safe)")

    # Initialize Benzinga client
    if settings.BENZINGA_API_KEY:
        benzinga_client = BenzingaClient(
            base_url=settings.BENZINGA_BASE_URL,
            api_key=settings.BENZINGA_API_KEY
        )
        logger.info("✅ Benzinga client initialized")
    else:
        logger.warning("⚠️ Benzinga API key not configured")

    # Start position monitoring background task (simple rules)
    asyncio.create_task(auto_monitor_positions())
    logger.info("✅ Position monitoring started (simple rules)")

    # Initialize and start smart position manager (LLM-powered exits)
    pm = init_position_manager(check_interval=30, min_analysis_interval=120)
    asyncio.create_task(pm.start())
    logger.info("✅ Smart Position Manager started (LLM-powered exits)")

    # Load auto-trade state and start background loop
    load_auto_trade_state()
    asyncio.create_task(auto_trade_loop())
    logger.info(f"✅ Auto-trade loop started (enabled={_auto_trade_enabled})")

    logger.info("="*60)

    yield

    # Shutdown
    logger.info("Shutting down AI Trading System")


# Create FastAPI app
app = FastAPI(
    title="AI Trading Intelligence System",
    description="Real-time market data from Benzinga + AI signals + Alpaca trading",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Trading System API",
        "version": "1.0.0",
        "benzinga_connected": benzinga_client is not None,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ALPACA_ENV,
        "paper_trading": settings.is_paper_trading,
        "benzinga_connected": benzinga_client is not None
    }


@app.get("/status")
async def system_status():
    """Get system status and configuration."""
    return {
        "trading_env": settings.ALPACA_ENV,
        "is_paper": settings.is_paper_trading,
        "risk_settings": {
            "max_position_risk": settings.TRADING_DEFAULT_MAX_POSITION_RISK,
            "daily_max_drawdown": settings.TRADING_DAILY_MAX_DRAWDOWN,
            "min_signal_score": settings.TRADING_MIN_SIGNAL_SCORE
        },
        "watchlist": settings.watchlist,
        "hybrid_interval": settings.TRADING_HYBRID_INTERVAL_SECONDS,
        "api_keys_configured": {
            "benzinga": bool(settings.BENZINGA_API_KEY),
            "alpaca": bool(settings.ALPACA_API_KEY_ID and settings.ALPACA_API_SECRET_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY)
        }
    }


# ============= BENZINGA API ENDPOINTS =============

@app.get("/api/news")
async def get_news(
    ticker: Optional[str] = Query(None, description="Stock ticker(s), comma-separated"),
    channels: Optional[str] = Query(None, description="News channels to filter"),
    days_back: int = Query(1, description="Number of days to look back"),
    hours_back: int = Query(None, description="Hours to look back (overrides days_back)"),
    limit: int = Query(10, description="Maximum results")
):
    """Get real-time news from Benzinga."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # For global news (no ticker), limit to 1 hour and 15 results max for speed
    if not ticker:
        hours_back = hours_back or 1  # Default 1 hour for global
        limit = min(limit, 15)  # Cap at 15 for global news

    # Calculate date range (use hours if specified)
    if hours_back:
        published_gte = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S")
    else:
        published_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    try:
        result = await benzinga_client.get_news(
            tickers=ticker,
            channels=channels,
            published_gte=published_gte,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/earnings")
async def get_earnings(
    ticker: Optional[str] = Query(None, description="Stock ticker"),
    days_back: int = Query(90, description="Days to look back for past earnings"),
    days_ahead: int = Query(30, description="Days to look ahead for upcoming earnings"),
    importance_min: int = Query(0, description="Minimum importance (0-5)"),
    limit: int = Query(20, description="Maximum results")
):
    """Get earnings calendar from Benzinga (both past and upcoming)."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # Date range - look back for recent earnings AND ahead for upcoming
    date_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_lte = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    try:
        result = await benzinga_client.get_earnings(
            ticker=ticker,
            date_gte=date_gte,
            date_lte=date_lte,
            importance_gte=importance_min,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching earnings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ratings")
async def get_ratings(
    ticker: Optional[str] = Query(None, description="Stock ticker"),
    days_back: int = Query(7, description="Days to look back"),
    action: Optional[str] = Query(None, description="Rating action (upgrades, downgrades, etc.)"),
    limit: int = Query(20, description="Maximum results")
):
    """Get analyst ratings from Benzinga."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    date_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    result = await benzinga_client.get_ratings(
        ticker=ticker,
        date_gte=date_gte,
        rating_action=action,
        limit=limit
    )

    if "error" in result:
        # Return empty results instead of error for subscription issues
        if "403" in result.get("error", "") or "NOT_AUTHORIZED" in result.get("message", ""):
            return {
                "results": [],
                "message": "Ratings data requires a Benzinga Ratings subscription"
            }
        raise HTTPException(status_code=500, detail=result.get("message", "API error"))

    return result


@app.get("/api/consensus/{ticker}")
async def get_consensus(ticker: str):
    """Get consensus ratings for a specific ticker."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # Convert ticker to uppercase for consistency
    ticker = ticker.upper()
    result = await benzinga_client.get_consensus(ticker)

    if "error" in result:
        # Return empty results instead of error for subscription issues
        if "403" in result.get("error", "") or "NOT_AUTHORIZED" in result.get("message", ""):
            return {
                "results": [],
                "message": "Consensus data requires a Benzinga Consensus subscription"
            }
        raise HTTPException(status_code=500, detail=result.get("message", "API error"))

    return result


@app.get("/api/dashboard/{ticker}")
async def get_dashboard(ticker: str):
    """Aggregate market, agent, and risk data for a ticker."""
    service = DashboardService()
    try:
        return await service.get_dashboard_state(ticker)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to build dashboard for {ticker}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build dashboard payload") from exc


# ============= FAST SIGNAL ENDPOINT (NO API CALLS) =============

@app.get("/api/signal/fast/{ticker}")
async def get_fast_signal(ticker: str):
    """
    ULTRA-FAST signal endpoint - uses ONLY cached data and local Python analysis.
    NO external API calls. Target: <100ms response time.

    This is used for:
    - AI Agents panel (instant display)
    - Trade decision panel (instant recommendations)
    - Auto-trade logic (must be fast for real-time trading)
    """
    ticker = ticker.upper()

    try:
        # Get quote (fast - Alpaca is quick)
        quote_data = await get_quote(ticker)
        current_price = quote_data.get("price", 100)

        # Get bars for technical analysis (fast - Alpaca is quick)
        bars = await get_bars(ticker, timeframe="1H", limit=30)

        # Pure Python technical analysis (instant)
        from app.services.technical_indicators import analyze_technical
        technical = analyze_technical(ticker, current_price, bars)

        # Check sentiment cache (NO API call if not cached)
        cached_sentiment = _sentiment_cache.get(ticker)
        sentiment_score = 50  # Neutral default
        sentiment_label = "neutral"

        if cached_sentiment:
            cached_data, cache_time = cached_sentiment
            # Use cache if less than 5 minutes old
            if (datetime.utcnow() - cache_time).total_seconds() < 300:
                sentiment_score = cached_data.get("score", 50)
                sentiment_label = cached_data.get("sentiment", "neutral")

        # Combine scores: Technical weighted 60%, Sentiment 40%
        combined_score = (technical.score * 0.6) + (sentiment_score * 0.4)

        # Determine action
        if combined_score >= 70:
            action = "BUY"
            confidence = min(0.9, combined_score / 100)
        elif combined_score <= 30:
            action = "SELL"
            confidence = min(0.9, (100 - combined_score) / 100)
        else:
            action = "HOLD"
            confidence = 0.5

        # Build agent signals for the UI
        news_agent = {
            "score": sentiment_score,
            "sentiment": 1 if sentiment_score > 60 else -1 if sentiment_score < 40 else 0,
            "confidence": 0.7 if cached_sentiment else 0.3,
            "urgency": 0.5,
            "notes": f"Sentiment: {sentiment_label}" + (" (cached)" if cached_sentiment else " (no data)")
        }

        earnings_agent = {
            "score": 50,
            "sentiment": 0,
            "confidence": 0.3,
            "urgency": 0.2,
            "notes": "Earnings data from cache"
        }

        technical_agent = {
            "score": technical.score,
            "sentiment": 1 if technical.score > 55 else -1 if technical.score < 45 else 0,
            "confidence": technical.confidence / 100,
            "urgency": 0.7 if abs(technical.score - 50) > 20 else 0.3,
            "notes": f"{technical.trend} trend, RSI: {technical.rsi:.1f}"
        }

        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "fast_mode": True,
            "agents": {
                "news": news_agent,
                "earnings": earnings_agent,
                "technical": technical_agent
            },
            "decision": {
                "action": action,
                "ticker": ticker,
                "confidence": confidence,
                "score": round(combined_score),
                "entry_price": current_price,
                "stop_loss": round(current_price * 0.98, 2),
                "take_profit": round(current_price * 1.03, 2),
                "quantity": calculate_position_size(
                    price=current_price,
                    stop_loss_price=current_price * 0.98,
                    confidence=confidence,
                    signal_score=round(combined_score)
                ),
                "rationale": f"Technical: {technical.score}, Sentiment: {sentiment_score}"
            },
            "technicals": {
                "rsi": technical.rsi,
                "macd": technical.macd,
                "trend": technical.trend,
                "regime": technical.regime.value,
                "support": technical.support,
                "resistance": technical.resistance,
                "signals": technical.signals
            },
            "market": {
                "price": current_price,
                "change": quote_data.get("change", 0),
                "change_percent": quote_data.get("change_percent", 0)
            }
        }

    except Exception as e:
        logger.error(f"Fast signal error for {ticker}: {e}")
        # Return neutral signal on error - never block the UI
        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "fast_mode": True,
            "error": str(e),
            "agents": {
                "news": {"score": 50, "sentiment": 0, "confidence": 0, "urgency": 0, "notes": "Error"},
                "earnings": {"score": 50, "sentiment": 0, "confidence": 0, "urgency": 0, "notes": "Error"},
                "technical": {"score": 50, "sentiment": 0, "confidence": 0, "urgency": 0, "notes": "Error"}
            },
            "decision": {
                "action": "HOLD",
                "ticker": ticker,
                "confidence": 0,
                "score": 50,
                "rationale": "Error - defaulting to HOLD"
            }
        }


# ============= REAL-TIME PRICE ENDPOINT =============

# Alpaca data client for real quotes
_alpaca_data_client = None

def get_alpaca_data_client():
    """Get or create Alpaca data client for quotes."""
    global _alpaca_data_client
    if _alpaca_data_client is None:
        from alpaca.data.historical import StockHistoricalDataClient
        api_key = settings.ALPACA_API_KEY_ID
        secret_key = settings.ALPACA_API_SECRET_KEY
        if api_key and secret_key:
            _alpaca_data_client = StockHistoricalDataClient(api_key, secret_key)
    return _alpaca_data_client

@app.get("/api/quote/{ticker}")
async def get_quote(ticker: str):
    """Get real-time quote for a ticker from Alpaca."""
    ticker = ticker.upper()

    # Try to get real quote from Alpaca
    try:
        client = get_alpaca_data_client()
        if client:
            from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest, StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            current_price = 0
            prev_close = 0
            volume = 0
            source = "alpaca"

            # First try to get latest trade (more accurate for after hours)
            try:
                trade_request = StockLatestTradeRequest(symbol_or_symbols=[ticker])
                trades = client.get_stock_latest_trade(trade_request)
                if ticker in trades:
                    trade = trades[ticker]
                    current_price = float(trade.price) if trade.price else 0
                    volume = int(trade.size) if trade.size else 0
                    source = "alpaca_trade"
            except Exception as e:
                logger.debug(f"Failed to get latest trade for {ticker}: {e}")

            # Fallback to quote if no trade
            if current_price == 0:
                try:
                    request = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
                    quotes = client.get_stock_latest_quote(request)
                    if ticker in quotes:
                        quote = quotes[ticker]
                        bid = float(quote.bid_price) if quote.bid_price else 0
                        ask = float(quote.ask_price) if quote.ask_price else 0
                        if bid > 0 and ask > 0:
                            current_price = (bid + ask) / 2
                        elif bid > 0:
                            current_price = bid
                        elif ask > 0:
                            current_price = ask
                        source = "alpaca_quote"
                except Exception as e:
                    logger.debug(f"Failed to get quote for {ticker}: {e}")

            # Get previous day's close for change calculation
            if current_price > 0:
                try:
                    # Get the last 2 daily bars to find previous close
                    bars_request = StockBarsRequest(
                        symbol_or_symbols=[ticker],
                        timeframe=TimeFrame.Day,
                        limit=2
                    )
                    bars = client.get_stock_bars(bars_request)
                    if ticker in bars and bars[ticker]:
                        bar_list = list(bars[ticker])
                        if len(bar_list) >= 2:
                            # Previous day's close
                            prev_close = float(bar_list[-2].close)
                        elif len(bar_list) == 1:
                            # Use today's open as fallback
                            prev_close = float(bar_list[-1].open)
                except Exception as e:
                    logger.debug(f"Failed to get bars for change calc {ticker}: {e}")

            if current_price > 0:
                change = current_price - prev_close if prev_close > 0 else 0
                change_percent = (change / prev_close * 100) if prev_close > 0 else 0

                return {
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_percent, 2),
                    "volume": volume,
                    "prev_close": round(prev_close, 2) if prev_close > 0 else None,
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": source
                }
    except Exception as e:
        logger.warning(f"Failed to get Alpaca quote for {ticker}: {e}")

    # Fallback to simulated quotes (updated Dec 2024 prices)
    simulated_quotes = {
        "AAPL": {"price": 237.33, "change": 2.30, "change_pct": 0.98},
        "MSFT": {"price": 423.46, "change": 6.51, "change_pct": 1.56},
        "GOOGL": {"price": 171.04, "change": -1.20, "change_pct": -0.70},
        "TSLA": {"price": 352.56, "change": 8.90, "change_pct": 2.59},
        "NVDA": {"price": 179.92, "change": 2.94, "change_pct": 1.66},
        "META": {"price": 569.19, "change": -4.30, "change_pct": -0.75},
        "AMZN": {"price": 207.89, "change": 1.80, "change_pct": 0.87},
        "AMD": {"price": 138.35, "change": 1.20, "change_pct": 0.88},
    }

    if ticker in simulated_quotes:
        quote = simulated_quotes[ticker]
        return {
            "ticker": ticker,
            "price": quote["price"],
            "change": quote["change"],
            "change_percent": quote["change_pct"],
            "timestamp": datetime.utcnow().isoformat(),
            "source": "simulated"
        }
    else:
        base_price = random.uniform(50, 300)
        change = random.uniform(-5, 5)
        return {
            "ticker": ticker,
            "price": round(base_price, 2),
            "change": round(change, 2),
            "change_percent": round((change / base_price) * 100, 2),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "simulated"
        }

# ============= BARS/CHART DATA ENDPOINT =============

@app.get("/api/bars/{ticker}")
async def get_bars(
    ticker: str,
    timeframe: str = Query("1Min", description="Bar timeframe"),
    limit: int = Query(100, description="Number of bars")
):
    """Get real historical price bars from Alpaca."""
    ticker = ticker.upper()

    # Try to get real bars from Alpaca
    try:
        client = get_alpaca_data_client()
        if client:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            # Map timeframe string to Alpaca TimeFrame
            timeframe_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, TimeFrameUnit.Minute),
                "15Min": TimeFrame(15, TimeFrameUnit.Minute),
                "30Min": TimeFrame(30, TimeFrameUnit.Minute),
                "1H": TimeFrame.Hour,
                "1Hour": TimeFrame.Hour,
                "1D": TimeFrame.Day,
                "1Day": TimeFrame.Day,
            }

            tf = timeframe_map.get(timeframe, TimeFrame.Minute)

            # Calculate start time based on timeframe
            # Note: Don't set end time - Alpaca free tier doesn't allow recent SIP queries
            now = datetime.utcnow()

            if timeframe in ["1D", "1Day"]:
                start = now - timedelta(days=limit + 5)
            elif timeframe in ["1H", "1Hour"]:
                start = now - timedelta(hours=limit + 10)
            else:
                # For minute bars, go back 1 day to include today's trading
                start = now - timedelta(days=1)

            request = StockBarsRequest(
                symbol_or_symbols=[ticker],
                timeframe=tf,
                start=start,
                # Note: No end time - let Alpaca return up to current available data
            )

            bars_data = client.get_stock_bars(request)

            # Access bars from the BarSet object
            if hasattr(bars_data, 'data') and ticker in bars_data.data:
                bars_list = bars_data.data[ticker]
            elif ticker in bars_data:
                bars_list = list(bars_data[ticker])
            else:
                bars_list = None

            if bars_list:
                result = []
                # Import pytz for timezone conversion
                import pytz
                eastern = pytz.timezone('America/New_York')

                for i, bar in enumerate(bars_list[-limit:]):  # Get last N bars
                    bar_time = bar.timestamp
                    # Convert to Eastern time for display
                    bar_time_et = bar_time.astimezone(eastern)
                    # Format time based on timeframe
                    if timeframe in ["1D", "1Day"]:
                        t_str = bar_time_et.strftime("%m/%d")
                    elif timeframe in ["1H", "1Hour", "4Hour"]:
                        t_str = bar_time_et.strftime("%m/%d %-I%p").replace("AM", "am").replace("PM", "pm")
                    else:
                        # Minute bars - show 12-hour format with AM/PM
                        t_str = bar_time_et.strftime("%-I:%M%p").replace("AM", "am").replace("PM", "pm")

                    result.append({
                        "time": i,
                        "timestamp": bar_time.isoformat(),
                        "t": t_str,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "vwap": float(bar.vwap) if bar.vwap else None,
                        "trade_count": int(bar.trade_count) if bar.trade_count else None
                    })

                if result:
                    logger.info(f"Fetched {len(result)} real bars for {ticker}")
                    return result

    except Exception as e:
        logger.warning(f"Failed to get Alpaca bars for {ticker}: {e}")

    # Fallback to simulated bars if Alpaca fails
    logger.info(f"Using simulated bars for {ticker}")
    quote_data = await get_quote(ticker)
    base_price = quote_data.get("price", 100)

    interval_minutes = {
        "1Min": 1, "5Min": 5, "15Min": 15, "30Min": 30,
        "1H": 60, "1Hour": 60, "1D": 1440, "1Day": 1440
    }.get(timeframe, 1)

    bars = []
    current_price = base_price * 0.98
    now = datetime.utcnow()

    # Import pytz for timezone conversion
    import pytz
    eastern = pytz.timezone('America/New_York')

    for i in range(limit):
        bar_time = now - timedelta(minutes=interval_minutes * (limit - 1 - i))
        change_pct = random.uniform(-0.003, 0.0035)
        current_price = current_price * (1 + change_pct)

        high = current_price * (1 + random.uniform(0, 0.002))
        low = current_price * (1 - random.uniform(0, 0.002))
        open_price = current_price * (1 + random.uniform(-0.001, 0.001))

        # Convert to Eastern time for display
        bar_time_et = bar_time.replace(tzinfo=pytz.UTC).astimezone(eastern)
        if timeframe in ["1D", "1Day"]:
            t_str = bar_time_et.strftime("%m/%d")
        elif timeframe in ["1H", "1Hour", "4Hour"]:
            t_str = bar_time_et.strftime("%m/%d %-I%p").replace("AM", "am").replace("PM", "pm")
        else:
            # Minute bars - show 12-hour format with AM/PM
            t_str = bar_time_et.strftime("%-I:%M%p").replace("AM", "am").replace("PM", "pm")

        bars.append({
            "time": i,
            "timestamp": bar_time.isoformat(),
            "t": t_str,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(current_price, 2),
            "volume": random.randint(10000, 500000)
        })

    return bars


# ============= MARKET SENTIMENT ENDPOINT =============

@app.get("/api/sentiment/{ticker}")
async def get_sentiment(ticker: str):
    """Get aggregated sentiment for a ticker based on news and earnings."""
    # Convert ticker to uppercase for consistency
    ticker = ticker.upper()

    # Check cache first
    cache_key = ticker
    now = datetime.utcnow()
    if cache_key in _sentiment_cache:
        cached_data, cache_time = _sentiment_cache[cache_key]
        if (now - cache_time).total_seconds() < SENTIMENT_CACHE_TTL:
            logger.debug(f"Sentiment cache HIT for {ticker}")
            return cached_data

    if not benzinga_client:
        return {
            "ticker": ticker,
            "sentiment": "neutral",
            "score": 50,
            "message": "Benzinga API not configured"
        }

    # Fetch multiple data sources
    news_task = benzinga_client.get_news(tickers=ticker, limit=20)
    earnings_task = benzinga_client.get_earnings(ticker=ticker, limit=5)

    # Try ratings but don't fail if not available
    ratings_task = benzinga_client.get_ratings(ticker=ticker, limit=5)
    consensus_task = benzinga_client.get_consensus(ticker)

    # Execute in parallel
    news, earnings, ratings, consensus = await asyncio.gather(
        news_task, earnings_task, ratings_task, consensus_task,
        return_exceptions=True
    )

    # Calculate sentiment score using component-based system
    # Each component contributes to a weighted average, avoiding artificial extremes

    components = []  # List of (score, weight) tuples

    # === NEWS SENTIMENT (weight: 25%) ===
    # Analyze news with diminishing returns and deduplication
    news_score = 50  # Neutral baseline for this component
    if isinstance(news, dict) and "results" in news:
        news_items = news.get("results", [])[:10]
        positive_signals = 0
        negative_signals = 0
        seen_themes = set()  # Deduplicate similar headlines

        for item in news_items:
            title = item.get("title", "").lower()

            # Create a simple theme key to avoid counting same story multiple times
            theme_words = [w for w in ["upgrade", "downgrade", "beat", "miss", "earnings", "rating"] if w in title]
            theme_key = "_".join(sorted(theme_words)) if theme_words else title[:30]

            if theme_key in seen_themes:
                continue
            seen_themes.add(theme_key)

            # Score based on keywords
            if any(word in title for word in ["upgrade", "beat", "beats", "surge", "rally", "soar",
                                              "jump", "bullish", "outperform", "record", "breakthrough"]):
                positive_signals += 1
            elif any(word in title for word in ["downgrade", "miss", "misses", "plunge", "crash",
                                                "bearish", "underperform", "bankruptcy", "investigation"]):
                negative_signals += 1
            # Mild signals
            elif any(word in title for word in ["gain", "rise", "strong", "growth"]):
                positive_signals += 0.5
            elif any(word in title for word in ["fall", "drop", "loss", "weak", "concern", "decline"]):
                negative_signals += 0.5

        # Convert to score with diminishing returns (sqrt scaling)
        # Max ~3 strong signals move score significantly
        net_signals = positive_signals - negative_signals
        if net_signals > 0:
            news_score = 50 + min(25, 10 * (net_signals ** 0.7))  # Max ~75
        elif net_signals < 0:
            news_score = 50 - min(25, 10 * (abs(net_signals) ** 0.7))  # Min ~25

        if news_items:
            components.append((news_score, 0.25))

    # === EARNINGS SENTIMENT (weight: 30%) ===
    # Most recent earnings matter most
    earnings_score = 50
    if isinstance(earnings, dict) and "results" in earnings:
        earnings_items = earnings.get("results", [])[:3]
        earnings_signals = []

        for i, earning in enumerate(earnings_items):
            if earning.get("estimated_eps") and earning.get("actual_eps"):
                try:
                    estimated = float(earning["estimated_eps"])
                    actual = float(earning["actual_eps"])
                    if estimated != 0:
                        surprise_pct = (actual - estimated) / abs(estimated)
                        # Weight by recency (most recent = 1.0, older = 0.5, oldest = 0.25)
                        recency_weight = 1.0 / (2 ** i)
                        earnings_signals.append((surprise_pct, recency_weight))
                except (ValueError, TypeError):
                    pass

        if earnings_signals:
            # Weighted average of earnings surprises
            total_weight = sum(w for _, w in earnings_signals)
            weighted_surprise = sum(s * w for s, w in earnings_signals) / total_weight

            # Convert surprise % to score adjustment (10% beat = +15 points, capped)
            adjustment = max(-25, min(25, weighted_surprise * 150))
            earnings_score = 50 + adjustment
            components.append((earnings_score, 0.30))

    # === ANALYST RATINGS (weight: 25%) ===
    # Recent rating changes
    ratings_score = 50
    if isinstance(ratings, dict) and "results" in ratings:
        ratings_items = ratings.get("results", [])[:5]
        upgrades = 0
        downgrades = 0

        for rating in ratings_items:
            action = rating.get("rating_action", "").lower()
            if "upgrade" in action:
                upgrades += 1
            elif "downgrade" in action:
                downgrades += 1

        if upgrades or downgrades:
            # Net rating changes, with diminishing returns
            net = upgrades - downgrades
            if net > 0:
                ratings_score = 50 + min(20, 8 * net)  # Max ~70
            elif net < 0:
                ratings_score = 50 - min(20, 8 * abs(net))  # Min ~30
            components.append((ratings_score, 0.25))

    # === ANALYST CONSENSUS (weight: 20%) ===
    # Current overall consensus
    consensus_score = 50
    if isinstance(consensus, dict) and "results" in consensus:
        if consensus["results"]:
            cons = consensus["results"][0]
            rating = cons.get("consensus_rating", "").lower()

            if "strong buy" in rating:
                consensus_score = 72
            elif "buy" in rating:
                consensus_score = 65
            elif "hold" in rating or "neutral" in rating:
                consensus_score = 50
            elif "sell" in rating:
                consensus_score = 35
            elif "strong sell" in rating:
                consensus_score = 28

            components.append((consensus_score, 0.20))

    # === CALCULATE FINAL SCORE ===
    if components:
        total_weight = sum(w for _, w in components)
        sentiment_score = sum(s * w for s, w in components) / total_weight

        # Conviction bonus: when multiple components strongly agree, boost the score
        # This allows scores to reach 90+ when signals truly align
        if len(components) >= 3:
            component_scores_list = [s for s, _ in components]
            all_bullish = all(s >= 62 for s in component_scores_list)
            all_bearish = all(s <= 38 for s in component_scores_list)

            if all_bullish:
                # Strong agreement - boost proportionally to how bullish
                avg_above_neutral = sum(s - 50 for s in component_scores_list) / len(component_scores_list)
                conviction_bonus = min(12, avg_above_neutral * 0.5)
                sentiment_score += conviction_bonus
            elif all_bearish:
                # Strong bearish agreement
                avg_below_neutral = sum(50 - s for s in component_scores_list) / len(component_scores_list)
                conviction_penalty = min(12, avg_below_neutral * 0.5)
                sentiment_score -= conviction_penalty
    else:
        sentiment_score = 50  # No data = neutral

    # Round to 1 decimal place
    sentiment_score = round(sentiment_score, 1)

    # Allow full range but scores near extremes require genuine conviction
    sentiment_score = max(5, min(95, sentiment_score))

    # Determine sentiment label
    if sentiment_score >= 70:
        sentiment = "bullish"
    elif sentiment_score >= 60:
        sentiment = "slightly_bullish"
    elif sentiment_score <= 30:
        sentiment = "bearish"
    elif sentiment_score <= 40:
        sentiment = "slightly_bearish"
    else:
        sentiment = "neutral"

    # Build component breakdown for transparency
    component_scores = {}
    if isinstance(news, dict) and news.get("results"):
        component_scores["news"] = round(news_score, 1)
    if isinstance(earnings, dict) and earnings.get("results"):
        component_scores["earnings"] = round(earnings_score, 1)
    if isinstance(ratings, dict) and ratings.get("results"):
        component_scores["ratings"] = round(ratings_score, 1)
    if isinstance(consensus, dict) and consensus.get("results"):
        component_scores["consensus"] = round(consensus_score, 1)

    result = {
        "ticker": ticker,
        "sentiment": sentiment,
        "score": sentiment_score,
        "components": component_scores,
        "sources": {
            "news_analyzed": len(news.get("results", [])) if isinstance(news, dict) else 0,
            "earnings_analyzed": len(earnings.get("results", [])) if isinstance(earnings, dict) else 0,
            "ratings_analyzed": len(ratings.get("results", [])) if isinstance(ratings, dict) else 0,
            "has_consensus": bool(consensus.get("results")) if isinstance(consensus, dict) else False
        },
        "timestamp": datetime.utcnow().isoformat()
    }

    # Cache the result
    _sentiment_cache[ticker] = (result, datetime.utcnow())

    return result


# ============= UNIFIED PRODUCTION TRADING SYSTEM =============

async def _analyze_ticker_for_signal(ticker: str) -> dict:
    """Analyze a single ticker and return signal data."""
    try:
        # Get momentum and sentiment in parallel
        momentum_task = get_momentum_analysis(ticker)
        sentiment_task = get_sentiment(ticker)

        momentum, sentiment = await asyncio.gather(
            momentum_task, sentiment_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(momentum, Exception):
            logger.error(f"Momentum analysis failed for {ticker}: {momentum}")
            return None
        if isinstance(sentiment, Exception):
            logger.error(f"Sentiment analysis failed for {ticker}: {sentiment}")
            return None

        momentum_score = momentum["momentum_score"]
        ai_score = sentiment["score"]  # Benzinga sentiment (news, earnings, ratings)

        # OPTION B: Sentiment Primary + Momentum Boost
        # Base score = Sentiment (what drives catalysts)
        # Momentum confirms or warns, doesn't override

        base_score = ai_score  # Sentiment is primary
        momentum_boost = 0
        momentum_warning = False

        # Momentum confirms sentiment (both bullish or both bearish)
        if ai_score >= 60 and momentum_score >= 55:
            # Positive sentiment + price rising = boost
            momentum_boost = min((momentum_score - 50) / 5, 10)  # Up to +10 points
        elif ai_score >= 60 and momentum_score < 45:
            # Positive sentiment + price falling = warning (but still tradeable)
            momentum_boost = -5  # Small penalty
            momentum_warning = True
        elif ai_score < 40 and momentum_score < 45:
            # Negative sentiment + price falling = confirms bearish
            momentum_boost = 5

        combined_score = base_score + momentum_boost
        combined_score = max(0, min(100, combined_score))  # Clamp to 0-100

        # Determine action based on combined score
        # 70+ = BUY (matches scanner threshold)
        if combined_score >= 70:
            action = "BUY"
        elif combined_score >= 60:
            action = "HOLD"  # Watch closely
        else:
            action = "WAIT"

        # Get quote for all tickers (not just high-scoring ones)
        quote = await get_quote(ticker)
        current_price = quote.get("price", 100)

        # Always return a signal - let the frontend/execute logic decide thresholds
        # Calculate confidence for position sizing (normalize combined score to 0-1)
        signal_confidence = min(combined_score / 100, 0.95)
        stop_loss_price = round(current_price * 0.995, 2)

        return {
            "ticker": ticker,
            "action": action,
            "combined_score": round(combined_score, 1),
            "momentum_score": momentum_score,
            "ai_score": ai_score,
            "momentum_boost": round(momentum_boost, 1),
            "momentum_warning": momentum_warning,
            "entry_price": current_price,
            "stop_loss": stop_loss_price,  # -0.5%
            "take_profit": round(current_price * 1.015, 2),  # +1.5%
            "quantity": calculate_position_size(
                price=current_price,
                stop_loss_price=stop_loss_price,
                confidence=signal_confidence,
                signal_score=round(combined_score)
            ),
            "signals": momentum.get("signals", [])[:2],
            "strategy": "SENTIMENT" if momentum_boost >= 0 else "SENTIMENT_CAUTION",
            "urgency": "NOW" if combined_score >= 75 else ("SOON" if combined_score >= 70 else "WAIT"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return None


@app.get("/api/trading/best-signal")
async def get_best_trading_signal():
    """Get the SINGLE BEST trading signal from all sources (momentum + AI)."""

    # Scan configured watchlist tickers - uses env var WATCHLIST_TICKERS
    settings = get_settings()
    candidates = settings.watchlist[:20]  # Limit to top 20 for performance

    # Fallback to defaults if watchlist is empty
    if not candidates:
        candidates = ["TSLA", "NVDA", "AMD", "AAPL", "META", "GOOGL", "MSFT"]

    logger.info(f"🔍 Scanning {len(candidates)} tickers: {candidates[:5]}...")

    # Analyze all tickers in parallel for speed
    results = await asyncio.gather(
        *[_analyze_ticker_for_signal(ticker) for ticker in candidates],
        return_exceptions=True
    )

    # Find best signal from results
    best_signal = None
    best_score = 0

    for result in results:
        if result is None or isinstance(result, Exception):
            continue
        if result.get("combined_score", 0) > best_score:
            best_signal = result
            best_score = result["combined_score"]

    # If no good signal, return wait status
    if not best_signal:
        return {
            "action": "WAIT",
            "message": "No strong trading signals detected",
            "timestamp": datetime.utcnow().isoformat()
        }

    return best_signal


# Cache for all decisions
_all_decisions_cache = {"data": None, "timestamp": 0}
ALL_DECISIONS_CACHE_TTL = 20  # Cache for 20 seconds (real-time trading)

@app.get("/api/trading/all-decisions")
async def get_all_trade_decisions():
    """Get trade decisions for ALL watchlist tickers (grouped by BUY/HOLD/SELL)."""
    global _all_decisions_cache

    now = datetime.utcnow().timestamp()

    # Check cache
    if _all_decisions_cache["data"] and (now - _all_decisions_cache["timestamp"]) < ALL_DECISIONS_CACHE_TTL:
        return _all_decisions_cache["data"]

    settings = get_settings()
    # Use watchlist tickers
    tickers = settings.watchlist[:50]  # Limit to 50 for performance

    # Analyze all tickers in parallel
    results = await asyncio.gather(
        *[_analyze_ticker_for_signal(ticker) for ticker in tickers],
        return_exceptions=True
    )

    # Group by action
    buy_decisions = []
    hold_decisions = []
    sell_decisions = []

    for result in results:
        if result is None or isinstance(result, Exception):
            continue

        action = result.get("action", "HOLD")
        decision = {
            "ticker": result.get("ticker"),
            "action": action,
            "confidence": result.get("combined_score", 50) / 100,
            "combinedScore": result.get("combined_score", 50),
            "aiScore": result.get("ai_score", 50),
            "momentumScore": result.get("momentum_score", 50),
            "strategy": result.get("strategy", "UNKNOWN"),
            "urgency": result.get("urgency", "WAIT"),
            "entryPrice": result.get("entry_price", 0),
            "stopLoss": result.get("stop_loss", 0),
            "takeProfit": result.get("take_profit", 0),
        }

        if action == "BUY":
            buy_decisions.append(decision)
        elif action == "SELL":
            sell_decisions.append(decision)
        else:
            hold_decisions.append(decision)

    # Sort each group by combined score (descending)
    buy_decisions.sort(key=lambda x: x["combinedScore"], reverse=True)
    hold_decisions.sort(key=lambda x: x["combinedScore"], reverse=True)
    sell_decisions.sort(key=lambda x: x["combinedScore"], reverse=True)

    response = {
        "timestamp": datetime.utcnow().isoformat(),
        "total": len(buy_decisions) + len(hold_decisions) + len(sell_decisions),
        "buy": buy_decisions,
        "hold": hold_decisions,
        "sell": sell_decisions,
        "counts": {
            "buy": len(buy_decisions),
            "hold": len(hold_decisions),
            "sell": len(sell_decisions),
        }
    }

    # Cache the result
    _all_decisions_cache = {"data": response, "timestamp": now}

    return response


# Rate limiting for trade execution
_last_trade_execution: dict = {"time": 0, "ticker": None}
TRADE_COOLDOWN_SECONDS = 60  # 1 minute between trades

@app.post("/api/trading/execute")
async def execute_trade(auto: bool = False, ticker: Optional[str] = None):
    """Execute a trade on Alpaca paper trading.

    If ticker is provided, analyze and trade that specific ticker.
    If ticker is not provided, use the best overall signal.
    """
    global _last_trade_execution

    # Rate limiting check
    now = datetime.utcnow().timestamp()
    time_since_last = now - _last_trade_execution["time"]
    if time_since_last < TRADE_COOLDOWN_SECONDS:
        remaining = int(TRADE_COOLDOWN_SECONDS - time_since_last)
        return {
            "status": "rate_limited",
            "message": f"Please wait {remaining}s before next trade",
            "cooldown_remaining": remaining
        }

    # Get signal for specific ticker or best overall
    if ticker:
        # Analyze the specific ticker requested
        signal = await _analyze_ticker_for_signal(ticker)
        if signal is None:
            return {
                "status": "error",
                "message": f"Failed to analyze {ticker}",
            }
        logger.info(f"[Execute] Analyzing specific ticker: {ticker} -> {signal.get('action')} ({signal.get('combined_score', 0):.1f})")
    else:
        # Get best signal from all candidates
        signal = await get_best_trading_signal()

    if signal.get("action") == "WAIT" or signal.get("action") == "HOLD":
        return {
            "status": "no_trade",
            "message": f"No actionable signal for {signal.get('ticker', 'unknown')} (action: {signal.get('action')})",
            "signal": signal
        }

    # Check if we already have a large position in this ticker
    ticker = signal.get("ticker")
    positions = alpaca_trader.get_positions()
    existing_position = next((p for p in positions if p["symbol"] == ticker), None)
    if existing_position and abs(existing_position.get("qty", 0)) >= 100:
        return {
            "status": "position_limit",
            "message": f"Already have {existing_position['qty']} shares of {ticker}. Close or reduce position first.",
            "existing_position": existing_position
        }

    # Execute on Alpaca
    if auto or signal.get("combined_score", 0) >= 75:
        # Update rate limit tracker BEFORE execution
        _last_trade_execution = {"time": now, "ticker": ticker}

        result = alpaca_trader.execute_trade(signal)

        # Log the trade execution
        log_activity(
            log_type="TRADE",
            ticker=signal.get("ticker", "UNKNOWN"),
            action=signal.get("action", "BUY"),
            details={
                "price": signal.get("price"),
                "quantity": result.get("qty") if result else None,
                "score": signal.get("combined_score"),
                "reasoning": signal.get("reasoning", "")[:200],  # Truncate long reasoning
                "order_id": result.get("id") if result else None,
                "status": "executed"
            }
        )

        return {
            "status": "executed",
            "signal": signal,
            "execution": result,
            "mode": "PAPER TRADING"
        }
    else:
        return {
            "status": "pending_confirmation",
            "signal": signal,
            "message": "Signal ready - confirm to execute"
        }


class ManualTradeRequest(BaseModel):
    """Request model for manual trades with full control."""
    ticker: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"  # "market", "limit", "stop", "bracket"
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    time_in_force: str = "day"  # "day", "gtc", "ioc", "fok"


@app.post("/api/trading/manual")
async def execute_manual_trade(trade: ManualTradeRequest):
    """
    Execute a manual trade with full user control.

    This bypasses AI recommendations and executes exactly what the user specifies.
    Supports market, limit, stop, and bracket orders.
    """
    global _last_trade_execution

    # Rate limiting check
    now = datetime.utcnow().timestamp()
    time_since_last = now - _last_trade_execution["time"]
    if time_since_last < TRADE_COOLDOWN_SECONDS:
        remaining = int(TRADE_COOLDOWN_SECONDS - time_since_last)
        return {
            "status": "rate_limited",
            "message": f"Please wait {remaining}s before next trade",
            "cooldown_remaining": remaining
        }

    # Validate inputs
    if trade.side not in ["buy", "sell"]:
        return {"status": "error", "message": "Side must be 'buy' or 'sell'"}

    if trade.quantity <= 0:
        return {"status": "error", "message": "Quantity must be positive"}

    if trade.order_type == "limit" and trade.limit_price is None:
        return {"status": "error", "message": "Limit price required for limit orders"}

    # Get current price for validation
    try:
        quote = alpaca_trader.get_quote(trade.ticker)
        current_price = quote.get("price", 0) if quote else 0
    except Exception:
        current_price = 0

    # Check if we have enough buying power
    account = alpaca_trader.get_account_status()
    if account:
        buying_power = float(account.get("buying_power", 0))
        estimated_cost = trade.quantity * (trade.limit_price or current_price or 100)
        if trade.side == "buy" and estimated_cost > buying_power:
            return {
                "status": "error",
                "message": f"Insufficient buying power. Need ${estimated_cost:,.2f}, have ${buying_power:,.2f}"
            }

    # Import Alpaca order types
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
    from alpaca.trading.requests import StopLossRequest, TakeProfitRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

    # Convert side string to enum
    order_side = OrderSide.BUY if trade.side.lower() == "buy" else OrderSide.SELL

    # Convert time_in_force string to enum
    tif = TimeInForce.DAY if trade.time_in_force.lower() == "day" else TimeInForce.GTC

    # Build order based on type
    if trade.order_type == "bracket" and trade.stop_loss and trade.take_profit:
        # Bracket order with stop loss and take profit
        order_request = MarketOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif,
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(stop_price=round(trade.stop_loss, 2)),
            take_profit=TakeProfitRequest(limit_price=round(trade.take_profit, 2))
        )
    elif trade.order_type == "limit":
        order_request = LimitOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif,
            limit_price=round(trade.limit_price, 2)
        )
    elif trade.order_type == "stop":
        order_request = StopOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif,
            stop_price=round(trade.stop_loss or trade.limit_price, 2)
        )
    else:
        # Market order
        order_request = MarketOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif
        )

    # Update rate limit tracker
    _last_trade_execution = {"time": now, "ticker": trade.ticker}

    # Execute the order
    try:
        result = alpaca_trader.client.submit_order(order_data=order_request)

        # Log the manual trade
        log_activity(
            log_type="MANUAL_TRADE",
            ticker=trade.ticker,
            action=trade.side.upper(),
            details={
                "quantity": trade.quantity,
                "order_type": trade.order_type,
                "limit_price": trade.limit_price,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "order_id": result.id if result else None,
                "status": "submitted"
            }
        )

        return {
            "status": "executed",
            "order": {
                "id": result.id,
                "symbol": result.symbol,
                "qty": str(result.qty),
                "side": result.side.value if hasattr(result.side, 'value') else str(result.side),
                "type": result.type.value if hasattr(result.type, 'value') else str(result.type),
                "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                "created_at": str(result.created_at)
            },
            "message": f"Manual {trade.side.upper()} order submitted for {trade.quantity} {trade.ticker}",
            "mode": "PAPER TRADING"  # Always paper trading for safety
        }
    except Exception as e:
        logger.error(f"Manual trade failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/api/trading/positions")
async def get_positions():
    """Get all open positions from Alpaca with associated stop/take profit orders."""
    positions = alpaca_trader.get_positions()

    # Get open orders to find stop loss and take profit legs
    open_orders = []
    if alpaca_trader.client:
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            open_orders = alpaca_trader.client.get_orders(filter=request)
        except Exception as e:
            logger.warning(f"Could not fetch open orders: {e}")

    # Map orders to positions
    for position in positions:
        ticker = position["symbol"]
        position["stop_loss"] = None
        position["take_profit"] = None

        # Find associated orders for this position
        for order in open_orders:
            if order.symbol != ticker:
                continue
            # Stop loss is a stop order
            if order.type.value == "stop" and order.stop_price:
                position["stop_loss"] = float(order.stop_price)
            # Take profit is a limit order (sell side for long positions)
            elif order.type.value == "limit" and order.limit_price:
                position["take_profit"] = float(order.limit_price)

        # Find entry time from filled buy orders
        position["entry_time"] = None
        for order in open_orders:
            pass  # open orders won't have fill time
        # Check closed/filled orders for entry time
        if alpaca_trader.client:
            try:
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus, OrderSide as OS
                filled_req = GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    symbols=[ticker],
                    side=OS.BUY,
                    limit=1,
                )
                filled_orders = alpaca_trader.client.get_orders(filter=filled_req)
                if filled_orders:
                    position["entry_time"] = str(filled_orders[0].filled_at) if filled_orders[0].filled_at else str(filled_orders[0].submitted_at)
            except Exception as e:
                logger.debug(f"Could not get entry time for {ticker}: {e}")

        # Check momentum for exit signals
        try:
            momentum = await get_momentum_analysis(ticker)

            # Add exit recommendation
            if momentum["momentum_score"] < 40:
                position["exit_signal"] = "MOMENTUM LOST - CONSIDER EXIT"
            elif position["pnl_pct"] >= 2:
                position["exit_signal"] = "TARGET HIT - TAKE PROFIT"
            elif position["pnl_pct"] <= -1:
                position["exit_signal"] = "STOP LOSS - EXIT NOW"
            else:
                position["exit_signal"] = None

        except:
            position["exit_signal"] = None

    return {
        "positions": positions,
        "count": len(positions),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/trading/close/{ticker}")
async def close_position(ticker: str, reason: str = "manual"):
    """Close a position."""
    result = alpaca_trader.close_position(ticker.upper())

    # Log the position exit
    log_activity(
        log_type="EXIT",
        ticker=ticker.upper(),
        action="CLOSE",
        details={
            "reason": reason,
            "pnl": result.get("pnl") if isinstance(result, dict) else None,
            "result": result.get("status") if isinstance(result, dict) else str(result)
        }
    )

    return result

@app.post("/api/trading/reduce/{ticker}")
async def reduce_position(ticker: str, quantity: int = 100):
    """Reduce a position by a specific quantity."""
    result = alpaca_trader.reduce_position(ticker.upper(), quantity)

    log_activity(
        log_type="REDUCE",
        ticker=ticker.upper(),
        action="REDUCE",
        details={
            "reduced_qty": quantity,
            "result": result.get("status") if isinstance(result, dict) else str(result)
        }
    )

    return result

@app.post("/api/trading/close-all")
async def close_all_positions():
    """Emergency: Close ALL positions."""
    result = alpaca_trader.close_all_positions()

    log_activity(
        log_type="EMERGENCY",
        ticker="ALL",
        action="CLOSE_ALL",
        details={"result": result.get("status") if isinstance(result, dict) else str(result)}
    )

    return result

# ============================================================
# AUTO-EXIT MONITORING
# ============================================================
EXIT_CONFIG = {
    "stop_loss_pct": -2.0,      # Exit if loss exceeds 2%
    "take_profit_pct": 5.0,     # Exit if profit exceeds 5%
    "momentum_exit": 35,        # Exit if momentum drops below 35
    "trailing_stop_pct": 1.5,   # Trailing stop: 1.5% from peak
}

# Track peak prices for trailing stops
_position_peaks: dict = {}

# Track tickers with pending exit orders to avoid duplicates
_pending_exit_orders: set = set()

async def check_position_exits():
    """Check all positions for exit signals and auto-close if needed."""
    global _pending_exit_orders

    positions = alpaca_trader.get_positions()
    exits_triggered = []

    # Get all pending orders to check which tickers already have exit orders
    try:
        if alpaca_trader.client:
            pending_orders = alpaca_trader.client.get_orders(status="open")
            tickers_with_pending = {order.symbol for order in pending_orders}
        else:
            tickers_with_pending = set()
    except Exception as e:
        logger.warning(f"Could not fetch pending orders: {e}")
        tickers_with_pending = _pending_exit_orders  # Use cached set

    for position in positions:
        ticker = position["symbol"]
        pnl_pct = position.get("pnl_pct", 0) * 100  # Convert to percentage
        current_price = position.get("current", 0)
        entry_price = position.get("entry", 0)

        # Skip if this ticker already has a pending order
        if ticker in tickers_with_pending or ticker in _pending_exit_orders:
            logger.debug(f"Skipping {ticker} - already has pending exit order")
            continue

        exit_reason = None

        # 1. Stop Loss Check
        if pnl_pct <= EXIT_CONFIG["stop_loss_pct"]:
            exit_reason = f"STOP_LOSS ({pnl_pct:.2f}%)"

        # 2. Take Profit Check
        elif pnl_pct >= EXIT_CONFIG["take_profit_pct"]:
            exit_reason = f"TAKE_PROFIT ({pnl_pct:.2f}%)"

        # 3. Trailing Stop Check
        else:
            # Track peak price
            if ticker not in _position_peaks or current_price > _position_peaks[ticker]:
                _position_peaks[ticker] = current_price

            peak = _position_peaks[ticker]
            if peak > 0:
                drawdown_from_peak = ((peak - current_price) / peak) * 100
                if drawdown_from_peak >= EXIT_CONFIG["trailing_stop_pct"] and pnl_pct > 0:
                    exit_reason = f"TRAILING_STOP (peak: ${peak:.2f}, drawdown: {drawdown_from_peak:.2f}%)"

        # 4. Momentum Check (only if in profit and no other exit triggered)
        if not exit_reason and pnl_pct > 0:
            try:
                momentum = await get_momentum_analysis(ticker)
                if momentum.get("momentum_score", 50) < EXIT_CONFIG["momentum_exit"]:
                    exit_reason = f"MOMENTUM_EXIT (score: {momentum.get('momentum_score')})"
            except:
                pass

        # Execute exit if triggered
        if exit_reason:
            logger.info(f"🚨 EXIT TRIGGERED: {ticker} - {exit_reason}")

            # Mark as pending BEFORE attempting to close
            _pending_exit_orders.add(ticker)

            result = alpaca_trader.close_position(ticker)

            # Check if order was successful
            if isinstance(result, dict):
                if result.get("status") == "error":
                    # Order failed - remove from pending
                    _pending_exit_orders.discard(ticker)
                    logger.warning(f"Exit order failed for {ticker}: {result.get('message')}")
                    # Don't log failed exits to avoid spam
                    continue
                elif result.get("status") in ["closed", "executed"]:
                    # Order succeeded - log it
                    log_activity(
                        log_type="AUTO_EXIT",
                        ticker=ticker,
                        action="CLOSE",
                        details={
                            "reason": exit_reason,
                            "pnl_pct": pnl_pct,
                            "entry": entry_price,
                            "exit_price": current_price,
                            "result": result.get("status")
                        }
                    )
                    exits_triggered.append({
                        "ticker": ticker,
                        "reason": exit_reason,
                        "pnl_pct": pnl_pct,
                        "result": result
                    })
                    # Clean up peak tracking
                    if ticker in _position_peaks:
                        del _position_peaks[ticker]
                    # Remove from pending after successful close
                    _pending_exit_orders.discard(ticker)

    return exits_triggered

@app.post("/api/trading/check-exits")
async def manual_check_exits():
    """Manually trigger exit check for all positions."""
    exits = await check_position_exits()
    return {
        "exits_triggered": len(exits),
        "details": exits,
        "config": EXIT_CONFIG,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/trading/exit-config")
async def get_exit_config():
    """Get current exit configuration."""
    return EXIT_CONFIG

@app.put("/api/trading/exit-config")
async def update_exit_config(
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    momentum_exit: int = None,
    trailing_stop_pct: float = None
):
    """Update exit configuration."""
    if stop_loss_pct is not None:
        EXIT_CONFIG["stop_loss_pct"] = stop_loss_pct
    if take_profit_pct is not None:
        EXIT_CONFIG["take_profit_pct"] = take_profit_pct
    if momentum_exit is not None:
        EXIT_CONFIG["momentum_exit"] = momentum_exit
    if trailing_stop_pct is not None:
        EXIT_CONFIG["trailing_stop_pct"] = trailing_stop_pct

    return {"status": "updated", "config": EXIT_CONFIG}

@app.get("/api/trading/account")
async def get_account():
    """Get Alpaca account status."""
    return alpaca_trader.get_account_status()


@app.get("/api/trading/orders")
async def get_orders(
    status: Optional[str] = Query("all", description="Order status: open, closed, all"),
    limit: int = Query(50, description="Maximum orders to return"),
    days: int = Query(7, description="Days to look back")
):
    """Get trade/order history from Alpaca."""
    if not alpaca_trader.client:
        # Return simulated orders if no client
        return {
            "orders": [
                {
                    "id": "sim-001",
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 10,
                    "filled_qty": 10,
                    "type": "market",
                    "status": "filled",
                    "filled_avg_price": 234.50,
                    "submitted_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "filled_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "pnl": 28.50,
                    "pnl_pct": 1.22
                },
                {
                    "id": "sim-002",
                    "symbol": "NVDA",
                    "side": "buy",
                    "qty": 5,
                    "filled_qty": 5,
                    "type": "market",
                    "status": "filled",
                    "filled_avg_price": 142.30,
                    "submitted_at": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
                    "filled_at": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
                    "pnl": -15.75,
                    "pnl_pct": -2.21
                },
                {
                    "id": "sim-003",
                    "symbol": "TSLA",
                    "side": "sell",
                    "qty": 8,
                    "filled_qty": 8,
                    "type": "market",
                    "status": "filled",
                    "filled_avg_price": 351.20,
                    "submitted_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "filled_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "pnl": 124.80,
                    "pnl_pct": 4.44
                }
            ],
            "count": 3,
            "status": "simulated",
            "timestamp": datetime.utcnow().isoformat()
        }

    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        # Map status string to enum
        status_map = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL
        }
        query_status = status_map.get(status, QueryOrderStatus.ALL)

        # Get orders
        request = GetOrdersRequest(
            status=query_status,
            limit=limit,
            after=datetime.utcnow() - timedelta(days=days)
        )

        orders = alpaca_trader.client.get_orders(filter=request)

        order_list = []
        for order in orders:
            order_data = {
                "id": str(order.id),
                "symbol": order.symbol,
                "side": order.side.value if hasattr(order.side, 'value') else str(order.side),
                "qty": float(order.qty) if order.qty else 0,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "type": order.type.value if hasattr(order.type, 'value') else str(order.type),
                "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "limit_price": float(order.limit_price) if order.limit_price else None,
                "stop_price": float(order.stop_price) if order.stop_price else None,
            }
            order_list.append(order_data)

        return {
            "orders": order_list,
            "count": len(order_list),
            "status": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return {
            "orders": [],
            "count": 0,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/portfolio/history")
async def get_portfolio_history(
    period: str = Query("1M", description="Period: 1D, 1W, 1M, 3M, 1A, all"),
    timeframe: str = Query("1D", description="Timeframe: 1Min, 5Min, 15Min, 1H, 1D")
):
    """Get portfolio value history from Alpaca."""
    if not alpaca_trader.client:
        return {"error": "No Alpaca connection", "data": []}

    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest

        req = GetPortfolioHistoryRequest(period=period, timeframe=timeframe)
        history = alpaca_trader.client.get_portfolio_history(req)

        # Convert to list of data points
        data_points = []
        for i, ts in enumerate(history.timestamp):
            data_points.append({
                "timestamp": ts,
                "date": datetime.fromtimestamp(ts).isoformat(),
                "equity": history.equity[i] if history.equity else 0,
                "profit_loss": history.profit_loss[i] if history.profit_loss else 0,
                "profit_loss_pct": (history.profit_loss_pct[i] * 100) if history.profit_loss_pct else 0,
            })

        # Calculate summary stats
        if data_points:
            start_equity = data_points[0]["equity"]
            end_equity = data_points[-1]["equity"]
            total_return = ((end_equity - start_equity) / start_equity * 100) if start_equity else 0
            max_equity = max(d["equity"] for d in data_points)
            min_equity = min(d["equity"] for d in data_points)
            max_drawdown = ((max_equity - min_equity) / max_equity * 100) if max_equity else 0

            # Find best and worst days
            best_day = max(data_points, key=lambda x: x["profit_loss_pct"])
            worst_day = min(data_points, key=lambda x: x["profit_loss_pct"])

            summary = {
                "start_equity": start_equity,
                "end_equity": end_equity,
                "total_return_pct": round(total_return, 2),
                "total_return_dollars": round(end_equity - start_equity, 2),
                "max_equity": max_equity,
                "min_equity": min_equity,
                "max_drawdown_pct": round(max_drawdown, 2),
                "best_day": {"date": best_day["date"], "pct": round(best_day["profit_loss_pct"], 2)},
                "worst_day": {"date": worst_day["date"], "pct": round(worst_day["profit_loss_pct"], 2)},
                "trading_days": len(data_points),
            }
        else:
            summary = {}

        return {
            "data": data_points,
            "summary": summary,
            "period": period,
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching portfolio history: {e}")
        return {
            "error": str(e),
            "data": [],
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/trading/closed-trades")
async def get_closed_trades(
    limit: int = Query(50, description="Maximum trades to return"),
    days_back: int = Query(None, description="Filter trades to last N days (None = all time)")
):
    """Get closed trades with P&L from Alpaca order history."""
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        if not alpaca_trader.client:
            return {"trades": [], "count": 0, "summary": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl_pct": 0}, "timestamp": datetime.utcnow().isoformat()}

        # Calculate date range
        if days_back:
            after_date = datetime.utcnow() - timedelta(days=days_back)
        else:
            after_date = datetime.utcnow() - timedelta(days=30)  # Default to 30 days

        # Fetch filled orders from Alpaca
        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            after=after_date,
            limit=500  # Fetch more to find matching pairs
        )
        orders = alpaca_trader.client.get_orders(filter=request)

        # Group orders by symbol to match BUY/SELL pairs (round trips)
        symbol_orders = {}
        for order in orders:
            if order.status.value != "filled":
                continue
            symbol = order.symbol
            if symbol not in symbol_orders:
                symbol_orders[symbol] = {"buys": [], "sells": []}

            order_data = {
                "id": str(order.id),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else 0,
            }

            if order.side.value == "buy":
                symbol_orders[symbol]["buys"].append(order_data)
            else:
                symbol_orders[symbol]["sells"].append(order_data)

        # Match BUY/SELL pairs to create closed trades (round trips)
        closed_trades = []
        for symbol, orders_dict in symbol_orders.items():
            buys = sorted(orders_dict["buys"], key=lambda x: x["filled_at"] or "")
            sells = sorted(orders_dict["sells"], key=lambda x: x["filled_at"] or "")

            # Simple matching: pair oldest buy with oldest sell
            while buys and sells:
                buy = buys.pop(0)
                sell = sells.pop(0)

                entry_price = buy["filled_avg_price"]
                exit_price = sell["filled_avg_price"]
                qty = min(buy["filled_qty"], sell["filled_qty"])

                if entry_price > 0 and exit_price > 0:
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    pnl_dollars = (exit_price - entry_price) * qty

                    closed_trades.append({
                        "id": sell["id"],
                        "symbol": symbol,
                        "side": "sell",
                        "timestamp": sell["filled_at"],
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(exit_price, 2),
                        "quantity": qty,
                        "pnl_pct": round(pnl_pct, 2),
                        "pnl_dollars": round(pnl_dollars, 2),
                        "reason": "Round trip",
                        "status": "closed"
                    })

        # Sort by timestamp descending (most recent first)
        closed_trades.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        # Calculate summary stats
        total_pnl_pct = sum(t.get("pnl_pct", 0) for t in closed_trades)
        total_pnl_dollars = sum(t.get("pnl_dollars", 0) for t in closed_trades)
        wins = len([t for t in closed_trades if (t.get("pnl_pct") or 0) > 0])
        losses = len([t for t in closed_trades if (t.get("pnl_pct") or 0) < 0])
        win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0

        return {
            "trades": closed_trades[:limit],
            "count": len(closed_trades),
            "summary": {
                "total_trades": len(closed_trades),
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
                "total_pnl_pct": round(total_pnl_pct, 2),
                "total_pnl_dollars": round(total_pnl_dollars, 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching closed trades: {e}")
        import traceback
        traceback.print_exc()
        return {"trades": [], "count": 0, "summary": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl_pct": 0}, "error": str(e), "timestamp": datetime.utcnow().isoformat()}


@app.delete("/api/trading/orders")
async def cancel_all_orders():
    """Cancel all open orders."""
    if not alpaca_trader.client:
        return {"status": "simulated", "message": "No Alpaca connection"}

    try:
        alpaca_trader.client.cancel_orders()
        return {
            "status": "success",
            "message": "All open orders cancelled",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cancelling orders: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.delete("/api/trading/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel a specific order by ID."""
    if not alpaca_trader.client:
        return {"status": "simulated", "message": "No Alpaca connection"}

    try:
        alpaca_trader.client.cancel_order_by_id(order_id)
        return {
            "status": "success",
            "message": f"Order {order_id} cancelled",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Activity log storage - persisted to file
ACTIVITY_LOG_FILE = Path(__file__).parent.parent / "data" / "activity_log.json"
_activity_log = []

def _load_activity_log():
    """Load activity log from file on startup."""
    global _activity_log
    try:
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if ACTIVITY_LOG_FILE.exists():
            with open(ACTIVITY_LOG_FILE, 'r') as f:
                _activity_log = json.load(f)
            logger.info(f"Loaded {len(_activity_log)} activity log entries from disk")
    except Exception as e:
        logger.error(f"Failed to load activity log: {e}")
        _activity_log = []

def _save_activity_log():
    """Save activity log to file."""
    try:
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ACTIVITY_LOG_FILE, 'w') as f:
            json.dump(_activity_log, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save activity log: {e}")

# Load on module import
_load_activity_log()


def log_activity(log_type: str, ticker: str, action: str, details: dict):
    """Add an entry to the activity log and persist to disk."""
    import uuid
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.utcnow().isoformat(),
        "type": log_type,
        "ticker": ticker,
        "action": action,
        "details": details
    }
    _activity_log.insert(0, entry)  # Most recent first
    _save_activity_log()  # Persist immediately


@app.get("/api/trading/activity-log")
async def get_activity_log(limit: int = Query(50, description="Max entries to return")):
    """Get trading activity log (entries, exits, signals)."""
    logs = _activity_log[:limit]
    return {
        "logs": logs,
        "total": len(_activity_log),
        "filtered": len(logs),
        "timestamp": datetime.utcnow().isoformat()
    }


# ============= POSITION MANAGEMENT WITH AUTO-EXIT =============

# Global position tracking for momentum monitoring
position_momentum = {}
exit_signals = {}

@app.post("/api/trading/monitor-positions")
async def monitor_positions_for_exit():
    """Monitor all positions for exit conditions (momentum loss, targets hit)."""
    positions = alpaca_trader.get_positions()

    exit_actions = []

    for position in positions:
        ticker = position["symbol"]
        entry_price = position["entry"]
        current_price = position["current"]
        pnl_pct = position["pnl_pct"]

        # Get current momentum
        momentum_data = await get_momentum_analysis(ticker)
        current_momentum = momentum_data["momentum_score"]

        # Track momentum history
        if ticker not in position_momentum:
            position_momentum[ticker] = {
                "peak_momentum": current_momentum,
                "entry_momentum": current_momentum,
                "momentum_history": [current_momentum]
            }
        else:
            position_momentum[ticker]["momentum_history"].append(current_momentum)
            position_momentum[ticker]["peak_momentum"] = max(
                position_momentum[ticker]["peak_momentum"],
                current_momentum
            )

        # Check exit conditions
        should_exit = False
        exit_reason = ""

        # 1. Momentum loss (drops below 40% from peak or below 30 absolute)
        momentum_loss = position_momentum[ticker]["peak_momentum"] - current_momentum
        if momentum_loss > 40 or current_momentum < 30:
            should_exit = True
            exit_reason = f"Momentum lost (current: {current_momentum}, peak: {position_momentum[ticker]['peak_momentum']})"

        # 2. Stop loss hit (2% loss)
        elif pnl_pct < -2:
            should_exit = True
            exit_reason = f"Stop loss hit ({pnl_pct:.2f}%)"

        # 3. Take profit hit (5% gain for fast momentum, 10% for normal)
        elif current_momentum > 70 and pnl_pct > 5:  # Fast momentum trade
            should_exit = True
            exit_reason = f"Fast momentum target hit (+{pnl_pct:.2f}%)"
        elif pnl_pct > 10:  # Normal take profit
            should_exit = True
            exit_reason = f"Take profit hit (+{pnl_pct:.2f}%)"

        # 4. Trailing stop for winners (protect 50% of gains after 3% profit)
        elif pnl_pct > 3:
            # Use trailing stop - exit if we lose 50% of gains
            max_pnl = max(position_momentum[ticker].get("max_pnl", pnl_pct), pnl_pct)
            position_momentum[ticker]["max_pnl"] = max_pnl

            if pnl_pct < (max_pnl * 0.5):
                should_exit = True
                exit_reason = f"Trailing stop hit (peak: +{max_pnl:.2f}%, current: +{pnl_pct:.2f}%)"

        if should_exit:
            exit_actions.append({
                "ticker": ticker,
                "action": "CLOSE",
                "reason": exit_reason,
                "current_price": current_price,
                "pnl_pct": pnl_pct,
                "momentum": current_momentum,
                "auto_execute": True
            })

            # Store exit signal for WebSocket broadcast
            exit_signals[ticker] = {
                "timestamp": datetime.utcnow().isoformat(),
                "reason": exit_reason,
                "pnl_pct": pnl_pct
            }

    # Execute exits if any
    executed_exits = []
    for exit_action in exit_actions:
        if exit_action["auto_execute"]:
            result = alpaca_trader.close_position(exit_action["ticker"])
            executed_exits.append({
                **exit_action,
                "execution_result": result
            })

            # Log the automatic exit
            log_activity(
                log_type="EXIT",
                ticker=exit_action["ticker"],
                action="SELL",
                details={
                    "reason": exit_action["reason"],
                    "pnl_pct": exit_action["pnl_pct"],
                    "momentum": exit_action["momentum"],
                    "price": exit_action["current_price"],
                    "auto": True
                }
            )

            # Clean up tracking
            if exit_action["ticker"] in position_momentum:
                del position_momentum[exit_action["ticker"]]

    return {
        "monitored_positions": len(positions),
        "exit_signals": exit_actions,
        "executed_exits": executed_exits,
        "momentum_tracking": {
            ticker: {
                "current": data["momentum_history"][-1] if data["momentum_history"] else 0,
                "peak": data["peak_momentum"],
                "entry": data["entry_momentum"]
            }
            for ticker, data in position_momentum.items()
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/trading/position-momentum/{ticker}")
async def get_position_momentum(ticker: str):
    """Get momentum tracking for a specific position."""
    ticker = ticker.upper()

    if ticker not in position_momentum:
        return {
            "error": f"No position tracking for {ticker}",
            "status": "not_found"
        }

    tracking = position_momentum[ticker]

    # Get current momentum
    momentum_data = await get_momentum_analysis(ticker)

    return {
        "ticker": ticker,
        "current_momentum": momentum_data["momentum_score"],
        "peak_momentum": tracking["peak_momentum"],
        "entry_momentum": tracking["entry_momentum"],
        "momentum_change": momentum_data["momentum_score"] - tracking["entry_momentum"],
        "momentum_from_peak": momentum_data["momentum_score"] - tracking["peak_momentum"],
        "history": tracking["momentum_history"][-20:],  # Last 20 data points
        "exit_signal": exit_signals.get(ticker),
        "recommendation": "HOLD" if momentum_data["momentum_score"] > 40 else "CONSIDER_EXIT",
        "timestamp": datetime.utcnow().isoformat()
    }

# Background task for continuous position monitoring
async def auto_monitor_positions():
    """Background task that monitors positions every 30 seconds for exits."""
    while True:
        try:
            if is_market_open():
                # Only monitor if we have positions (avoid unnecessary API calls)
                positions = alpaca_trader.get_positions() if alpaca_trader else []
                if positions:
                    # Check for automatic exits (stop-loss, take-profit, trailing, momentum)
                    exits = await check_position_exits()
                    if exits:
                        logger.info(f"🚨 AUTO-EXITS TRIGGERED: {len(exits)} positions closed")
                        for exit in exits:
                            logger.info(f"   - {exit['ticker']}: {exit['reason']} (P&L: {exit['pnl_pct']:.2f}%)")
                    else:
                        logger.debug(f"Position monitoring: {len(positions)} positions, no exits triggered")
            await asyncio.sleep(30)  # Check every 30 seconds for day trading
        except Exception as e:
            logger.error(f"Error in position monitoring: {e}")
            await asyncio.sleep(30)

# Start position monitoring on startup (integrated into lifespan)

# ============= AUTO-TRADE BACKGROUND LOOP =============

async def auto_trade_loop():
    """Background task that automatically scans and trades when enabled."""
    global _auto_trade_enabled

    while True:
        try:
            if _auto_trade_enabled and is_market_open():
                logger.info("🤖 [AUTO-TRADE] Running automatic trade scan...")

                # Get best signal - check BOTH watchlist scan AND best-signal endpoint
                try:
                    settings = get_settings()
                    min_score = 70  # STRICT: Only trade signals with score >= 70

                    # FIRST: Check watchlist scan for BUY recommendations (matches UI)
                    scan_result = await scan_watchlist()
                    buy_opportunities = scan_result.get("top_opportunities", [])

                    signal = None
                    score = 0
                    action = "WAIT"

                    # Get current positions to skip tickers we already own
                    positions = alpaca_trader.get_positions() if alpaca_trader else []
                    owned_symbols = {p["symbol"] for p in positions}

                    if buy_opportunities:
                        # Iterate through BUY opportunities to find one we don't already own
                        for opp in buy_opportunities:
                            ticker = opp["ticker"]
                            score = opp["score"]
                            action = opp["recommendation"]

                            if ticker in owned_symbols:
                                logger.info(f"🤖 [AUTO-TRADE] Skipping {ticker} (score: {score}) - already have position")
                                continue

                            logger.info(f"🤖 [AUTO-TRADE] Found scan BUY signal: {ticker} (score: {score})")

                            # Get full signal data for this ticker
                            signal = await _analyze_ticker_for_signal(ticker)
                            if signal:
                                signal["combined_score"] = score  # Use scan score
                                signal["action"] = action
                            break
                        else:
                            # All buy opportunities already owned
                            logger.info(f"🤖 [AUTO-TRADE] All {len(buy_opportunities)} BUY signals already owned, checking fallback")
                            signal = await get_best_trading_signal()
                            score = signal.get("combined_score", 0) if signal else 0
                            action = signal.get("action", "WAIT") if signal else "WAIT"
                    else:
                        # FALLBACK: Use best-signal endpoint
                        signal = await get_best_trading_signal()
                        score = signal.get("combined_score", 0) if signal else 0
                        action = signal.get("action", "WAIT") if signal else "WAIT"

                    # Execute on BUY signals OR strong HOLD signals (don't miss opportunities)
                    should_trade = (
                        signal and
                        score >= min_score and
                        action in ["BUY", "HOLD"]  # HOLD with high score = still good opportunity
                    )

                    if should_trade:
                        ticker = signal.get("ticker")
                        trade_score = float(signal.get("combined_score", 0))

                        # Double-check we don't already own this ticker
                        if ticker in owned_symbols:
                            logger.info(f"🤖 [AUTO-TRADE] Skipping {ticker} - already have position")
                        else:
                            # Execute the trade
                            logger.info(f"🤖 [AUTO-TRADE] Executing BUY on {ticker} (score: {trade_score:.1f})")
                            result = alpaca_trader.execute_trade(signal)

                            # Register with position manager for smart exit tracking
                            pm = get_position_manager()
                            if pm and result and result.get("status") == "executed":
                                pm.register_entry(
                                    symbol=ticker,
                                    entry_price=signal.get("price", result.get("entry_price", 0)),
                                    quantity=result.get("quantity", 1),
                                    thesis=signal.get("reasoning", "")[:500],
                                    stop_loss=result.get("stop_loss"),
                                    take_profit=result.get("take_profit"),
                                )
                                logger.info(f"🤖 [AUTO-TRADE] Registered {ticker} with Position Manager for exit tracking")

                            # Log the trade
                            log_activity(
                                log_type="AUTO_TRADE",
                                ticker=ticker,
                                action="BUY",
                                details={
                                    "price": signal.get("entry_price"),
                                    "quantity": result.get("quantity") if result else None,
                                    "score": trade_score,
                                    "reasoning": (signal.get("reasoning") or "")[:200],
                                    "order_id": result.get("order_id") if result else None,
                                    "status": result.get("status") if result else None,
                                    "auto": True
                                }
                            )
                            logger.info(f"🤖 [AUTO-TRADE] ✅ Trade executed: {result}")
                    else:
                        # Log why we didn't trade
                        reason = "no signal" if not signal else f"action={action}, score={float(score):.1f} (need {min_score}+)"
                        logger.info(f"🤖 [AUTO-TRADE] No trade - {reason}")

                except Exception as e:
                    logger.error(f"🤖 [AUTO-TRADE] Error getting signal: {e}")

            elif _auto_trade_enabled and not is_market_open():
                logger.debug("🤖 [AUTO-TRADE] Market closed, skipping scan")

            # Wait for next interval
            await asyncio.sleep(_auto_trade_interval)

        except Exception as e:
            logger.error(f"🤖 [AUTO-TRADE] Loop error: {e}")
            await asyncio.sleep(_auto_trade_interval)


# ============= POSITION MANAGER API ENDPOINTS =============

@app.get("/api/position-manager/status")
async def get_position_manager_status():
    """Get smart position manager status and tracked positions."""
    pm = get_position_manager()
    if not pm:
        return {"status": "not_initialized"}
    return pm.get_status()


@app.post("/api/position-manager/register")
async def register_position_entry(
    symbol: str,
    entry_price: float,
    quantity: float,
    thesis: Optional[str] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
):
    """Manually register a position entry for smart exit tracking."""
    pm = get_position_manager()
    if not pm:
        raise HTTPException(status_code=500, detail="Position manager not initialized")

    pm.register_entry(
        symbol=symbol.upper(),
        entry_price=entry_price,
        quantity=quantity,
        thesis=thesis,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    return {
        "status": "registered",
        "symbol": symbol.upper(),
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "message": f"Position {symbol} registered for smart exit management"
    }


@app.get("/api/position-manager/analyze/{symbol}")
async def analyze_position_exit(symbol: str):
    """Run LLM exit analysis for a specific position."""
    from app.services.agents.exit_strategy_agent import ExitStrategyAgent
    from app.services.position_manager import calculate_atr
    from app.services.technical_indicators import analyze_technical

    symbol = symbol.upper()
    positions = alpaca_trader.get_positions()
    position = next((p for p in positions if p["symbol"] == symbol), None)

    if not position:
        raise HTTPException(status_code=404, detail=f"No position found for {symbol}")

    pm = get_position_manager()
    pos_state = pm.state.positions.get(symbol) if pm else None

    current_price = position.get("current", 0)
    entry_price = pos_state.entry_price if pos_state else position.get("entry", 0)
    days_held = pos_state.days_held if pos_state else 0

    # Get bars for technical analysis
    bars = await pm._get_bars(symbol) if pm else []
    atr = calculate_atr(bars) if bars else current_price * 0.02

    tech_signal = analyze_technical(symbol, current_price, bars) if bars else None
    technical_data = {
        "rsi": tech_signal.rsi if tech_signal else 50,
        "trend": tech_signal.trend if tech_signal else "neutral",
        "momentum": tech_signal.momentum if tech_signal else "flat",
        "sma_20": tech_signal.sma_20 if tech_signal else current_price,
        "sma_50": tech_signal.sma_50 if tech_signal else current_price,
    }

    # Run exit analysis
    exit_plan = await ExitStrategyAgent.analyze_with_cache(
        ticker=symbol,
        position={
            "qty": position.get("qty"),
            "unrealized_pl": position.get("pnl", 0),
            "unrealized_plpc": position.get("pnl_pct", 0),
        },
        current_price=current_price,
        entry_price=entry_price,
        entry_thesis=pos_state.entry_thesis if pos_state else None,
        days_held=days_held,
        atr=atr,
        technical_data=technical_data,
        original_stop_loss=pos_state.original_stop_loss if pos_state else None,
        original_take_profit=pos_state.original_take_profit if pos_state else None,
        force=True,  # Force fresh analysis
    )

    return {
        "symbol": symbol,
        "position": position,
        "exit_analysis": exit_plan.to_dict(),
        "recommendation": {
            "action": exit_plan.action.value,
            "urgency": exit_plan.urgency.value,
            "stop_loss": exit_plan.stop_loss,
            "take_profit_levels": exit_plan.take_profit_levels,
            "reasoning": exit_plan.reasoning,
        }
    }


# ============= AUTO-TRADE API ENDPOINTS =============

@app.get("/api/auto-trade/status")
async def get_auto_trade_status():
    """Get current auto-trade status."""
    return {
        "enabled": _auto_trade_enabled,
        "interval": _auto_trade_interval,
        "market_open": is_market_open(),
        "updated_at": datetime.utcnow().isoformat()
    }


@app.post("/api/auto-trade/enable")
async def enable_auto_trade(interval: int = 60):
    """Enable auto-trading with specified interval (seconds)."""
    global _auto_trade_enabled, _auto_trade_interval

    _auto_trade_enabled = True
    _auto_trade_interval = max(30, min(300, interval))  # Clamp between 30s and 5min
    save_auto_trade_state()

    logger.info(f"🤖 [AUTO-TRADE] ENABLED with {_auto_trade_interval}s interval")

    return {
        "status": "enabled",
        "enabled": True,
        "interval": _auto_trade_interval,
        "message": f"Auto-trading enabled. Will scan every {_auto_trade_interval}s when market is open."
    }


@app.post("/api/auto-trade/disable")
async def disable_auto_trade():
    """Disable auto-trading."""
    global _auto_trade_enabled

    _auto_trade_enabled = False
    save_auto_trade_state()

    logger.info("🤖 [AUTO-TRADE] DISABLED")

    return {
        "status": "disabled",
        "enabled": False,
        "message": "Auto-trading disabled. No automatic trades will be executed."
    }


# ============= MOMENTUM TRADING & FLASH SIGNALS =============

@app.get("/api/momentum/{ticker}")
async def get_momentum_analysis(ticker: str):
    """Ultra-fast momentum analysis for quick trades."""
    ticker = ticker.upper()

    # Check cache first
    now = datetime.utcnow()
    if ticker in _momentum_cache:
        cached_data, cache_time = _momentum_cache[ticker]
        if (now - cache_time).total_seconds() < MOMENTUM_CACHE_TTL:
            logger.debug(f"Momentum cache HIT for {ticker}")
            return cached_data

    # Get real-time data
    quote_data = await get_quote(ticker)

    # Quick news check (last hour only for speed)
    if benzinga_client:
        news = await benzinga_client.get_news(
            tickers=ticker,
            published_gte=(datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            limit=5
        )
    else:
        news = {"results": []}

    # Calculate momentum score (0-100)
    momentum_score = 50
    signals = []

    # Price momentum - continuous scaling based on daily change
    price_change = quote_data.get("change_percent", 0)

    # Scale price change to momentum points (each 1% = ~8 points, capped)
    price_momentum = price_change * 8
    price_momentum = max(-30, min(30, price_momentum))  # Cap at +/- 30 points
    momentum_score += price_momentum

    # Add descriptive signals based on magnitude
    if price_change > 3:
        signals.append("🚀 STRONG UPWARD MOMENTUM")
    elif price_change > 1.5:
        signals.append("📈 POSITIVE MOMENTUM")
    elif price_change > 0.5:
        signals.append("📈 SLIGHT UPWARD")
    elif price_change < -3:
        signals.append("📉 STRONG DOWNWARD MOMENTUM")
    elif price_change < -1.5:
        signals.append("⬇️ NEGATIVE MOMENTUM")
    elif price_change < -0.5:
        signals.append("⬇️ SLIGHT DOWNWARD")

    # Breaking news momentum
    news_items = news.get("results", [])
    if news_items:
        # Count recent news (any news in last hour counts)
        recent_count = len(news_items)
        if recent_count > 0:
            # More news = more momentum (capped)
            news_boost = min(10, recent_count * 3)
            momentum_score += news_boost
            signals.append(f"📰 {recent_count} recent news items")

            # Check news sentiment quickly
            bullish_count = 0
            bearish_count = 0
            for item in news_items[:5]:
                title = item.get("title", "").lower()
                if any(word in title for word in ["surge", "soar", "jump", "breakthrough", "beat", "upgrade", "bullish", "rally"]):
                    bullish_count += 1
                elif any(word in title for word in ["crash", "plunge", "fall", "miss", "warning", "downgrade", "bearish", "drop"]):
                    bearish_count += 1

            # Net news sentiment
            net_sentiment = bullish_count - bearish_count
            if net_sentiment > 0:
                momentum_score += min(10, net_sentiment * 5)
                signals.append(f"💥 {bullish_count} BULLISH headlines")
            elif net_sentiment < 0:
                momentum_score -= min(10, abs(net_sentiment) * 5)
                signals.append(f"⚠️ {bearish_count} BEARISH headlines")

    # Volatility indicator
    if abs(price_change) > 2:
        signals.append("🔥 HIGH VOLATILITY")
    elif abs(price_change) > 1:
        signals.append("📊 MODERATE ACTIVITY")

    # Cap score
    momentum_score = max(10, min(90, momentum_score))  # Don't allow extreme 0 or 100

    # Generate instant trade decision
    if momentum_score >= 75:
        action = "🟢 BUY NOW"
        urgency = "IMMEDIATE"
        strategy = "MOMENTUM SCALP"
    elif momentum_score >= 65:
        action = "🟡 BUY READY"
        urgency = "QUICK"
        strategy = "QUICK TRADE"
    elif momentum_score <= 25:
        action = "🔴 SELL/SHORT"
        urgency = "IMMEDIATE"
        strategy = "EXIT NOW"
    elif momentum_score <= 35:
        action = "🟠 SELL READY"
        urgency = "QUICK"
        strategy = "REDUCE/EXIT"
    else:
        action = "⚪ NO ACTION"
        urgency = "WAIT"
        strategy = "MONITOR"

    current_price = quote_data.get("price", 100)

    result = {
        "ticker": ticker,
        "momentum_score": momentum_score,
        "action": action,
        "urgency": urgency,
        "strategy": strategy,
        "signals": signals,

        # Quick trade parameters
        "flash_trade": {
            "entry_price": current_price,
            "quick_target": round(current_price * 1.01, 2),  # 1% quick profit
            "scalp_target": round(current_price * 1.02, 2),  # 2% scalp target
            "momentum_target": round(current_price * 1.03, 2),  # 3% momentum target
            "stop_loss": round(current_price * 0.995, 2),  # 0.5% tight stop
            "time_limit": "5-15 minutes",
            "exit_on": "Momentum loss or target hit"
        },

        # Momentum indicators
        "momentum_status": {
            "strength": "STRONG" if abs(momentum_score - 50) > 25 else "MODERATE" if abs(momentum_score - 50) > 15 else "WEAK",
            "direction": "UP" if momentum_score > 50 else "DOWN" if momentum_score < 50 else "FLAT",
            "speed": "FAST" if len(signals) >= 3 else "NORMAL",
            "news_driven": len(news_items) > 0,
            "price_change": f"{price_change:+.2f}%"
        },

        # Exit conditions
        "exit_triggers": [
            "Momentum score drops below 40" if momentum_score > 50 else "Momentum score rises above 60",
            "Price reverses 0.5% from entry",
            "5 minutes without continued momentum",
            "Target hit or stop triggered"
        ],

        "timestamp": datetime.utcnow().isoformat(),
        "analysis_time": "< 1 second"
    }

    # Cache the result
    _momentum_cache[ticker] = (result, now)

    return result

@app.get("/api/momentum/scan")
async def momentum_scanner():
    """Scan all tickers for momentum opportunities RIGHT NOW."""
    hot_tickers = ["TSLA", "NVDA", "AMD", "AAPL", "META", "GOOGL", "MSFT", "AMZN"]

    momentum_alerts = []

    for ticker in hot_tickers:
        try:
            momentum = await get_momentum_analysis(ticker)

            if momentum["momentum_score"] >= 65 or momentum["momentum_score"] <= 35:
                momentum_alerts.append({
                    "ticker": ticker,
                    "score": momentum["momentum_score"],
                    "action": momentum["action"],
                    "urgency": momentum["urgency"],
                    "signals": momentum["signals"][:2],  # Top 2 signals
                    "entry": momentum["flash_trade"]["entry_price"],
                    "target": momentum["flash_trade"]["quick_target"],
                    "stop": momentum["flash_trade"]["stop_loss"]
                })
        except:
            pass

    # Sort by urgency
    momentum_alerts.sort(key=lambda x: abs(x["score"] - 50), reverse=True)

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "alerts_count": len(momentum_alerts),
        "hot_trades": momentum_alerts[:3],  # Top 3 opportunities
        "all_alerts": momentum_alerts,
        "market_status": "🔥 HOT" if len(momentum_alerts) >= 3 else "⚡ ACTIVE" if len(momentum_alerts) >= 1 else "😴 QUIET"
    }

# ============= AI INSIGHTS & ANALYSIS =============

@app.get("/api/ai/deep-analysis/{ticker}")
async def get_deep_ai_analysis(
    ticker: str,
    force: bool = Query(False, description="Force LLM calls even if cache is valid")
):
    """
    Get DEEP AI analysis using Claude + OpenAI agents WITH SMART CACHING.

    This endpoint runs the full multi-agent analysis:
    1. NewsIntelligenceAgent (Claude) - Deep news analysis
    2. TechnicalAnalysisAgent (OpenAI) - Technical signals
    3. SentimentSynthesisAgent (Claude) - Final trading decision

    LLMs are only called when:
    - No cached signal exists
    - Upstream data has changed since last run
    - Cache has expired
    - force=true is passed

    This keeps LLM costs low (~$40-80/month vs $150-200+).
    """
    ticker = ticker.upper()

    try:
        from app.services.ai_agents import run_full_analysis

        # Gather all data
        quote_data = await get_quote(ticker)
        current_price = quote_data.get("price", 100)

        # Get bars for technical analysis
        bars = await get_bars(ticker, timeframe="1H", limit=50)

        # Get news with timestamp for cache check
        latest_news_ts = None
        if benzinga_client:
            news_data = await benzinga_client.get_news(tickers=ticker, limit=10)
            news_items = news_data.get("results", [])
            # Extract latest news timestamp
            if news_items:
                newest = news_items[0]
                ts_str = newest.get("created", newest.get("published_at", ""))
                if ts_str:
                    try:
                        latest_news_ts = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
        else:
            news_items = []

        # Get earnings
        if benzinga_client:
            earnings_data = await benzinga_client.get_earnings(ticker=ticker, limit=3)
            earnings = earnings_data.get("results", [{}])[0] if earnings_data.get("results") else None
        else:
            earnings = None

        # Get account and positions
        account = alpaca_trader.get_account_status()
        positions_data = alpaca_trader.get_positions()

        # Calculate technical indicators (simple versions)
        closes = [b.get("close", 0) for b in bars[-20:]] if bars else []
        rsi = calculate_rsi(closes) if len(closes) >= 14 else None
        macd = calculate_macd(closes) if len(closes) >= 26 else None
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        sma_50 = sum([b.get("close", 0) for b in bars[-50:]]) / 50 if len(bars) >= 50 else None

        # Run full AI analysis WITH CACHING
        result = await run_full_analysis(
            ticker=ticker,
            news_items=news_items,
            current_price=current_price,
            bars=bars,
            rsi=rsi,
            macd=macd,
            sma_20=sma_20,
            sma_50=sma_50,
            earnings=earnings,
            account=account,
            positions=positions_data,
            latest_news_ts=latest_news_ts,
            force_llm=force,  # Pass force flag
        )

        return result

    except Exception as e:
        logger.error(f"Deep AI analysis error for {ticker}: {e}", exc_info=True)
        return {
            "ticker": ticker,
            "error": str(e),
            "final_action": "HOLD",
            "final_score": 50,
            "message": "AI analysis failed, using neutral stance"
        }


@app.get("/api/ai/quick-analysis/{ticker}")
async def get_quick_ai_analysis(ticker: str):
    """
    Get FAST analysis using only Python (NO LLM calls).

    This endpoint runs pure Python technical analysis without any LLM costs.
    Use this for the main loop / frequent updates.

    For deep analysis with LLMs, use /api/ai/deep-analysis/{ticker}.
    """
    ticker = ticker.upper()

    try:
        from app.services.ai_agents import run_quick_analysis

        # Get bars for technical analysis
        bars = await get_bars(ticker, timeframe="1H", limit=50)

        # Get current price
        quote_data = await get_quote(ticker)
        current_price = quote_data.get("price", 100)

        # Run quick analysis (no LLM)
        result = await run_quick_analysis(
            ticker=ticker,
            current_price=current_price,
            bars=bars,
        )

        return result

    except Exception as e:
        logger.error(f"Quick analysis error for {ticker}: {e}", exc_info=True)
        return {
            "ticker": ticker,
            "error": str(e),
            "score": 50,
            "message": "Quick analysis failed"
        }


@app.get("/api/ai/cache/status")
async def get_cache_status_endpoint(
    ticker: Optional[str] = Query(None, description="Specific ticker or None for overall stats")
):
    """
    Get agent cache status and statistics.

    This endpoint shows:
    - Cache hit/miss rates
    - LLM calls saved
    - Per-ticker cache status
    - Cache expiration times

    Use this to monitor LLM cost optimization.
    """
    from app.services.ai_agents import get_cache_status

    if ticker:
        return get_cache_status(ticker.upper())
    return get_cache_status()


@app.post("/api/ai/cache/clear")
async def clear_cache_endpoint(
    ticker: Optional[str] = Query(None, description="Specific ticker or None to clear all")
):
    """
    Clear agent caches.

    Use this to force fresh LLM analysis on next request.
    """
    from app.services.agent_cache import agent_cache

    if ticker:
        agent_cache.invalidate(ticker.upper())
        return {"message": f"Cache cleared for {ticker.upper()}"}
    else:
        agent_cache.invalidate_all()
        return {"message": "All caches cleared"}


def calculate_rsi(closes: list, period: int = 14) -> float:
    """Calculate RSI from closing prices."""
    if len(closes) < period + 1:
        return 50.0

    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(closes: list) -> dict:
    """Calculate MACD from closing prices."""
    if len(closes) < 26:
        return {"value": 0, "signal": 0, "histogram": 0}

    def ema(data, period):
        multiplier = 2 / (period + 1)
        ema_values = [data[0]]
        for price in data[1:]:
            ema_values.append((price * multiplier) + (ema_values[-1] * (1 - multiplier)))
        return ema_values[-1]

    ema_12 = ema(closes, 12)
    ema_26 = ema(closes, 26)
    macd_line = ema_12 - ema_26

    # Signal line (9-period EMA of MACD) - simplified
    signal = macd_line * 0.8  # Approximation

    return {
        "value": round(macd_line, 4),
        "signal": round(signal, 4),
        "histogram": round(macd_line - signal, 4)
    }


@app.get("/api/ai/analyze/{ticker}")
async def get_ai_analysis(ticker: str):
    """Get comprehensive AI analysis and insights for a ticker (legacy endpoint)."""
    ticker = ticker.upper()

    # Gather all available data
    sentiment_data = await get_sentiment(ticker)
    quote_data = await get_quote(ticker)

    # Fetch additional data for analysis
    news_task = benzinga_client.get_news(tickers=ticker, limit=10) if benzinga_client else None
    earnings_task = benzinga_client.get_earnings(ticker=ticker, limit=3) if benzinga_client else None

    if benzinga_client:
        news, earnings = await asyncio.gather(news_task, earnings_task, return_exceptions=True)
    else:
        news = earnings = None

    # Build comprehensive AI analysis
    analysis = {
        "ticker": ticker,
        "timestamp": datetime.utcnow().isoformat(),
        "current_price": quote_data.get("price"),
        "price_change": quote_data.get("change_percent"),

        # Overall AI Assessment
        "ai_score": sentiment_data.get("score"),
        "ai_sentiment": sentiment_data.get("sentiment"),
        "ai_recommendation": "STRONG BUY" if sentiment_data.get("score", 50) >= 85 else
                            "BUY" if sentiment_data.get("score", 50) >= 70 else
                            "HOLD" if sentiment_data.get("score", 50) >= 40 else
                            "SELL" if sentiment_data.get("score", 50) >= 15 else
                            "STRONG SELL",

        # Detailed Signal Analysis
        "signal_breakdown": {
            "technical_signals": {
                "momentum": "Bullish" if quote_data.get("change_percent", 0) > 1 else "Bearish" if quote_data.get("change_percent", 0) < -1 else "Neutral",
                "price_action": f"${quote_data.get('price', 0):.2f} ({quote_data.get('change_percent', 0):+.2f}%)",
                "trend": "Uptrend" if quote_data.get("change_percent", 0) > 0 else "Downtrend",
            },

            "sentiment_signals": {
                "news_sentiment": analyze_news_sentiment(news),
                "earnings_outlook": analyze_earnings_outlook(earnings),
                "social_buzz": "High" if sentiment_data.get("score", 50) > 70 else "Moderate" if sentiment_data.get("score", 50) > 50 else "Low",
            },

            "fundamental_signals": {
                "earnings_trend": "Positive" if earnings and has_positive_earnings_trend(earnings) else "Mixed",
                "analyst_consensus": "Bullish" if sentiment_data.get("score", 50) > 60 else "Neutral",
                "sector_momentum": "Strong" if ticker in ["NVDA", "MSFT", "GOOGL"] else "Moderate",
            }
        },

        # AI Reasoning & Logic
        "ai_reasoning": {
            "primary_factors": [],
            "risk_factors": [],
            "opportunity_factors": [],
            "confidence_level": "HIGH" if abs(sentiment_data.get("score", 50) - 50) > 30 else "MEDIUM" if abs(sentiment_data.get("score", 50) - 50) > 15 else "LOW",
        },

        # Actionable Insights
        "actionable_insights": {
            "entry_points": [],
            "exit_points": [],
            "position_sizing": "",
            "risk_management": "",
            "time_horizon": "",
        },

        # Decision Explanation
        "decision_explanation": "",
    }

    # Build AI reasoning based on score
    score = sentiment_data.get("score", 50)

    # Primary factors
    if score >= 70:
        analysis["ai_reasoning"]["primary_factors"] = [
            f"Strong bullish sentiment (score: {score})",
            f"Positive price momentum ({quote_data.get('change_percent', 0):+.2f}%)",
            "Multiple positive news catalysts detected",
            "Technical indicators favor upward movement"
        ]
        analysis["ai_reasoning"]["opportunity_factors"] = [
            "High probability of continued upward momentum",
            "Strong market sentiment supporting price appreciation",
            "Potential for breakout above resistance levels"
        ]
    elif score <= 30:
        analysis["ai_reasoning"]["primary_factors"] = [
            f"Strong bearish sentiment (score: {score})",
            "Negative news flow impacting stock",
            "Technical weakness detected",
            "Market sentiment turning negative"
        ]
        analysis["ai_reasoning"]["risk_factors"] = [
            "High probability of continued downward pressure",
            "Weak technical structure",
            "Negative catalysts outweigh positives"
        ]
    else:
        analysis["ai_reasoning"]["primary_factors"] = [
            f"Neutral market sentiment (score: {score})",
            "Mixed signals from news and data",
            "Consolidation phase likely",
            "Waiting for clearer direction"
        ]

    # Risk factors (always present)
    analysis["ai_reasoning"]["risk_factors"].extend([
        "Market volatility remains elevated",
        "Macro economic uncertainties",
        "Sector rotation risks"
    ])

    # Actionable insights based on AI score
    current_price = quote_data.get("price", 100)

    if score >= 70:
        analysis["actionable_insights"] = {
            "entry_points": [
                f"Immediate: ${current_price:.2f} (current)",
                f"On dip: ${current_price * 0.98:.2f} (-2%)",
                f"Breakout: ${current_price * 1.02:.2f} (+2%)"
            ],
            "exit_points": [
                f"Target 1: ${current_price * 1.05:.2f} (+5%)",
                f"Target 2: ${current_price * 1.10:.2f} (+10%)",
                f"Stop loss: ${current_price * 0.95:.2f} (-5%)"
            ],
            "position_sizing": "75-100% of planned allocation",
            "risk_management": "Use 5% stop loss, trail stops after +5% gain",
            "time_horizon": "2-4 weeks for full targets"
        }

        analysis["decision_explanation"] = f"""
        🤖 AI DECISION: BULLISH - RECOMMEND BUY

        The AI system has identified {ticker} as a strong buying opportunity based on:
        1. Sentiment score of {score}/100 indicates strong positive momentum
        2. Recent price action shows {quote_data.get('change_percent', 0):+.2f}% movement
        3. News analysis reveals {len(news.get('results', [])) if news else 0} recent positive catalysts
        4. Technical and fundamental factors align bullishly

        CONFIDENCE: {analysis['ai_reasoning']['confidence_level']}
        RISK/REWARD: Favorable (potential +10% upside vs -5% risk)
        """

    elif score <= 30:
        analysis["actionable_insights"] = {
            "entry_points": [
                "Not recommended at current levels",
                f"Wait for support at ${current_price * 0.90:.2f} (-10%)"
            ],
            "exit_points": [
                f"Exit existing positions at ${current_price:.2f}",
                f"Short target: ${current_price * 0.95:.2f} (-5%)"
            ],
            "position_sizing": "Reduce or exit positions",
            "risk_management": "Tight stops, consider hedging",
            "time_horizon": "Immediate action recommended"
        }

        analysis["decision_explanation"] = f"""
        🤖 AI DECISION: BEARISH - RECOMMEND SELL/AVOID

        The AI system warns against {ticker} based on:
        1. Weak sentiment score of {score}/100 indicates negative momentum
        2. Technical weakness and bearish patterns detected
        3. Negative news flow and deteriorating fundamentals
        4. High risk of further downside

        CONFIDENCE: {analysis['ai_reasoning']['confidence_level']}
        RISK/REWARD: Unfavorable (limited upside vs significant downside risk)
        """
    else:
        analysis["actionable_insights"] = {
            "entry_points": [
                f"Wait for breakout above ${current_price * 1.03:.2f}",
                f"Or support bounce at ${current_price * 0.97:.2f}"
            ],
            "exit_points": [
                f"Range top: ${current_price * 1.05:.2f}",
                f"Range bottom: ${current_price * 0.95:.2f}"
            ],
            "position_sizing": "25-50% of planned allocation",
            "risk_management": "Wide stops, wait for confirmation",
            "time_horizon": "Monitor for 1-2 weeks for clearer signals"
        }

        analysis["decision_explanation"] = f"""
        🤖 AI DECISION: NEUTRAL - HOLD/WAIT

        The AI system recommends patience with {ticker}:
        1. Mixed sentiment score of {score}/100 suggests consolidation
        2. Conflicting signals require more data
        3. No clear directional bias identified
        4. Better opportunities may exist elsewhere

        CONFIDENCE: {analysis['ai_reasoning']['confidence_level']}
        RISK/REWARD: Balanced (wait for better setup)
        """

    return analysis

def analyze_news_sentiment(news_data):
    """Analyze news sentiment from news data."""
    if not news_data or "results" not in news_data:
        return "No recent news"

    results = news_data.get("results", [])
    if not results:
        return "No recent news"

    positive_count = 0
    negative_count = 0

    for item in results[:10]:
        title = item.get("title", "").lower()
        if any(word in title for word in ["upgrade", "beat", "surge", "rally", "gain"]):
            positive_count += 1
        elif any(word in title for word in ["downgrade", "miss", "fall", "drop", "loss"]):
            negative_count += 1

    if positive_count > negative_count + 2:
        return f"Very Positive ({positive_count}+ articles)"
    elif positive_count > negative_count:
        return f"Positive ({positive_count} vs {negative_count})"
    elif negative_count > positive_count:
        return f"Negative ({negative_count} vs {positive_count})"
    else:
        return f"Mixed ({positive_count}/{negative_count})"

def analyze_earnings_outlook(earnings_data):
    """Analyze earnings outlook from earnings data."""
    if not earnings_data or "results" not in earnings_data:
        return "No upcoming earnings"

    results = earnings_data.get("results", [])
    if not results:
        return "No upcoming earnings"

    next_earnings = results[0]
    if next_earnings.get("importance", 0) >= 3:
        return f"High importance earnings soon"
    else:
        return "Regular earnings cycle"

def has_positive_earnings_trend(earnings_data):
    """Check if earnings show positive trend."""
    if not earnings_data or "results" not in earnings_data:
        return False

    for earning in earnings_data.get("results", [])[:3]:
        if earning.get("actual_eps") and earning.get("estimated_eps"):
            if earning["actual_eps"] > earning["estimated_eps"]:
                return True
    return False

# ============= WATCHLIST SCANNER =============

@app.get("/api/watchlist")
async def get_watchlist():
    """Return the configured watchlist tickers from .env."""
    return {
        "tickers": settings.watchlist,
        "universe": settings.universe,
        "spicy": settings.spicy,
        "high_volume": settings.high_volume,
        "all": settings.all_tickers,
        "count": {
            "watchlist": len(settings.watchlist),
            "universe": len(settings.universe),
            "spicy": len(settings.spicy),
            "high_volume": len(settings.high_volume),
            "total_unique": len(settings.all_tickers),
        }
    }


@app.get("/api/scan/watchlist")
async def scan_watchlist():
    """Scan all watchlist tickers for opportunities."""
    # Check cache first
    cache_key = "watchlist"
    now = datetime.utcnow()
    if cache_key in _scan_cache:
        cached_data, cache_time = _scan_cache[cache_key]
        if (now - cache_time).total_seconds() < SCAN_CACHE_TTL:
            logger.debug("Scan watchlist cache HIT")
            return cached_data

    if not benzinga_client:
        return {
            "message": "Benzinga API not configured",
            "watchlist": settings.watchlist
        }

    async def scan_ticker(ticker: str):
        """Scan a single ticker and return result."""
        try:
            sentiment_data = await get_sentiment(ticker)
            return {
                "ticker": ticker,
                "sentiment": sentiment_data["sentiment"],
                "score": sentiment_data["score"],
                "recommendation": "BUY" if sentiment_data["score"] >= 70 else
                                 "SELL" if sentiment_data["score"] <= 30 else "HOLD"
            }
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            return {
                "ticker": ticker,
                "sentiment": "unknown",
                "score": 50,
                "recommendation": "HOLD",
                "error": str(e)
            }

    # Run all scans in parallel for speed
    results = await asyncio.gather(*[scan_ticker(t) for t in settings.watchlist])
    results = list(results)

    # Sort by score (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)

    response = {
        "scan_time": datetime.utcnow().isoformat(),
        "watchlist_count": len(settings.watchlist),
        "results": results,
        "top_opportunities": [r for r in results if r["score"] >= 70],
        "warnings": [r for r in results if r["score"] <= 30]
    }

    # Cache the result
    _scan_cache[cache_key] = (response, now)
    return response


@app.get("/api/scan/universe")
async def scan_universe():
    """Scan extended momentum universe for opportunities."""
    if not benzinga_client:
        return {
            "message": "Benzinga API not configured",
            "universe": settings.universe
        }

    universe_tickers = settings.universe
    if not universe_tickers:
        return {
            "message": "No universe tickers configured",
            "universe": []
        }

    async def scan_ticker(ticker: str):
        """Scan a single ticker and return result."""
        try:
            sentiment_data = await get_sentiment(ticker)
            return {
                "ticker": ticker,
                "sentiment": sentiment_data["sentiment"],
                "score": sentiment_data["score"],
                "recommendation": "BUY" if sentiment_data["score"] >= 70 else
                                 "SELL" if sentiment_data["score"] <= 30 else "HOLD"
            }
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            return {
                "ticker": ticker,
                "sentiment": "unknown",
                "score": 50,
                "recommendation": "HOLD",
                "error": str(e)
            }

    # Run all scans in parallel for speed
    results = await asyncio.gather(*[scan_ticker(t) for t in universe_tickers])
    results = list(results)

    # Sort by score (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "universe_count": len(universe_tickers),
        "results": results,
        "top_opportunities": [r for r in results if r["score"] >= 70],
        "warnings": [r for r in results if r["score"] <= 30]
    }


@app.get("/api/scan/spicy")
async def scan_spicy():
    """Scan high-volatility spicy list for opportunities."""
    # Check cache first
    cache_key = "spicy"
    now = datetime.utcnow()
    if cache_key in _scan_cache:
        cached_data, cache_time = _scan_cache[cache_key]
        if (now - cache_time).total_seconds() < SCAN_CACHE_TTL:
            logger.debug("Scan spicy cache HIT")
            return cached_data

    if not benzinga_client:
        return {
            "message": "Benzinga API not configured",
            "spicy": settings.spicy
        }

    spicy_tickers = settings.spicy
    if not spicy_tickers:
        return {
            "message": "No spicy tickers configured",
            "spicy": []
        }

    async def scan_ticker(ticker: str):
        """Scan a single ticker and return result."""
        try:
            sentiment_data = await get_sentiment(ticker)
            return {
                "ticker": ticker,
                "sentiment": sentiment_data["sentiment"],
                "score": sentiment_data["score"],
                "recommendation": "BUY" if sentiment_data["score"] >= 75 else  # Higher threshold for spicy
                                 "SELL" if sentiment_data["score"] <= 25 else "HOLD",
                "risk_level": "HIGH",
                "warning": "High volatility - trade with caution"
            }
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            return {
                "ticker": ticker,
                "sentiment": "unknown",
                "score": 50,
                "recommendation": "HOLD",
                "risk_level": "HIGH",
                "error": str(e)
            }

    # Run all scans in parallel for speed
    results = await asyncio.gather(*[scan_ticker(t) for t in spicy_tickers])
    results = list(results)

    # Sort by score (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)

    response = {
        "scan_time": datetime.utcnow().isoformat(),
        "spicy_count": len(spicy_tickers),
        "results": results,
        "top_opportunities": [r for r in results if r["score"] >= 75],
        "warnings": [r for r in results if r["score"] <= 25],
        "risk_warning": "⚠️ SPICY LIST - High volatility stocks with elevated risk"
    }

    # Cache the result
    _scan_cache[cache_key] = (response, now)
    return response


# ============= WEBSOCKET =============

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast to all connections."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


@app.websocket("/ws/production")
async def websocket_production(websocket: WebSocket):
    """PRODUCTION WebSocket - ONE unified signal, auto-execution, position management."""
    await manager.connect(websocket)

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "🚀 PRODUCTION TRADING SYSTEM - PAPER MODE",
            "mode": "UNIFIED SIGNALS",
            "timestamp": datetime.utcnow().isoformat()
        })

        scan_counter = 0

        while True:
            try:
                # Check for commands
                data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)

                if data == "execute":
                    # Manual execution trigger
                    result = await execute_trade(auto=True)
                    await websocket.send_json({
                        "type": "execution",
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                elif data.startswith("close:"):
                    # Close position
                    ticker = data.split(":")[1].upper()
                    result = alpaca_trader.close_position(ticker)
                    await websocket.send_json({
                        "type": "position_closed",
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                scan_counter += 1

                # Every 10 seconds, scan for the BEST signal
                if scan_counter % 1 == 0:  # Every cycle (10 seconds)
                    # Get current positions first
                    positions = await get_positions()

                    # Get the single best signal
                    best_signal = await get_best_trading_signal()

                    # Check if we should execute
                    # Paper trading works 24/7, so we allow execution anytime
                    market_status = get_market_status()
                    is_paper_mode = True  # Alpaca is always in paper mode for safety
                    should_execute = (
                        best_signal.get("action") == "BUY" and
                        best_signal.get("combined_score", 0) >= 75 and
                        (is_market_open() or is_paper_mode)  # Paper mode allows 24/7 trading
                    )

                    # Send unified update
                    await websocket.send_json({
                        "type": "trading_update",

                        # THE ONE SIGNAL
                        "best_signal": best_signal,

                        # Current positions with exit signals
                        "positions": positions,

                        # Account status
                        "account": alpaca_trader.get_account_status(),

                        # Auto-execution status
                        "auto_execute": should_execute,
                        "execution_pending": should_execute and best_signal.get("action") == "BUY",

                        # Market status
                        "market_status": get_market_status(),

                        "timestamp": datetime.utcnow().isoformat(),
                        "next_scan": "10 seconds"
                    })

                    # Auto-execute if conditions met
                    if should_execute:
                        logger.info(f"🎯 AUTO-EXECUTING: {best_signal['ticker']} @ {best_signal['combined_score']:.1f}")
                        result = alpaca_trader.execute_trade(best_signal)
                        await websocket.send_json({
                            "type": "auto_execution",
                            "signal": best_signal,
                            "result": result,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        logger.info(f"✅ Execution result: {result}")
                    elif best_signal.get("combined_score", 0) >= 75 and best_signal.get("action") != "BUY":
                        logger.info(f"⏸️ Signal {best_signal['ticker']} score {best_signal['combined_score']:.1f} >= 75 but action is {best_signal.get('action')}")

                # Check for exit conditions on positions
                if scan_counter % 3 == 0:  # Every 30 seconds
                    positions = await get_positions()
                    for position in positions["positions"]:
                        if position.get("exit_signal"):
                            # Auto-exit if stop loss or strong signal
                            if "STOP LOSS" in position["exit_signal"] or "TARGET HIT" in position["exit_signal"]:
                                result = alpaca_trader.close_position(position["symbol"])
                                await websocket.send_json({
                                    "type": "auto_exit",
                                    "position": position,
                                    "reason": position["exit_signal"],
                                    "result": result,
                                    "timestamp": datetime.utcnow().isoformat()
                                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

def get_market_status():
    """Get current market status."""
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    et_hour = (now_utc.hour - 5) % 24
    weekday = now_utc.weekday()

    if weekday >= 5:
        return "closed_weekend"
    elif et_hour >= 4 and et_hour < 9:
        return "pre_market"
    elif et_hour == 9 and now_utc.minute >= 30:
        return "open"
    elif et_hour >= 10 and et_hour < 16:
        return "open"
    elif et_hour >= 16 and et_hour < 20:
        return "after_hours"
    else:
        return "closed"


def is_market_open() -> bool:
    """Check if the market is currently open."""
    status = get_market_status()
    return status == "open"

@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket for real-time AI signals with detailed analysis."""
    await manager.connect(websocket)
    signal_counter = 0

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to AI Trading Signals with Enhanced Insights",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Send periodic AI signals and analysis
        while True:
            try:
                # Wait for client message or timeout after 30 seconds
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Handle client requests for specific analysis
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                elif data.startswith("analyze:"):
                    # Client requested analysis for specific ticker
                    ticker = data.split(":")[1].upper()
                    analysis = await get_ai_analysis(ticker)
                    await websocket.send_json({
                        "type": "ai_analysis",
                        "ticker": ticker,
                        "analysis": analysis,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    # Echo for testing
                    await websocket.send_json({
                        "type": "echo",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                signal_counter += 1

                # Every 3rd heartbeat, send an AI signal instead
                if signal_counter % 3 == 0:
                    # Generate AI trading signal with detailed insights
                    watchlist = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN"]
                    ticker = random.choice(watchlist)

                    # Get quick sentiment
                    sentiment_data = await get_sentiment(ticker)
                    score = sentiment_data.get("score", 50)

                    # Build AI signal with reasoning
                    signal = {
                        "type": "ai_signal",
                        "ticker": ticker,
                        "action": "BUY" if score >= 70 else "SELL" if score <= 30 else "HOLD",
                        "strength": "STRONG" if abs(score - 50) > 30 else "MODERATE" if abs(score - 50) > 15 else "WEAK",
                        "ai_score": score,
                        "confidence": "HIGH" if abs(score - 50) > 30 else "MEDIUM" if abs(score - 50) > 15 else "LOW",

                        # AI Reasoning
                        "ai_insights": {
                            "decision": "BUY SIGNAL" if score >= 70 else "SELL SIGNAL" if score <= 30 else "NEUTRAL",
                            "reasoning": [
                                f"Sentiment score: {score}/100",
                                f"Market conditions: {'Favorable' if score > 50 else 'Challenging'}",
                                f"Technical setup: {'Bullish' if score >= 70 else 'Bearish' if score <= 30 else 'Consolidating'}",
                                f"News flow: {sentiment_data.get('sources', {}).get('news_analyzed', 0)} articles analyzed"
                            ],
                            "key_factors": [
                                f"Primary trend: {'Upward' if score > 60 else 'Downward' if score < 40 else 'Sideways'}",
                                f"Risk level: {'Low' if score > 70 else 'High' if score < 30 else 'Medium'}",
                                f"Time horizon: {'Short-term' if abs(score - 50) > 30 else 'Medium-term'}"
                            ],
                            "recommendation": f"{'Strong Buy' if score >= 85 else 'Buy' if score >= 70 else 'Hold' if score >= 40 else 'Sell' if score >= 15 else 'Strong Sell'}"
                        },

                        # Actionable data
                        "targets": {
                            "entry": f"Current market price",
                            "stop_loss": f"-5% from entry" if score > 50 else "-3% from entry",
                            "take_profit_1": f"+5% from entry" if score > 50 else "+3% from entry",
                            "take_profit_2": f"+10% from entry" if score > 70 else "+5% from entry"
                        },

                        "timestamp": datetime.utcnow().isoformat()
                    }

                    await websocket.send_json(signal)

                else:
                    # Regular heartbeat with market status
                    from datetime import timezone

                    # Get current time in Eastern Time
                    now_utc = datetime.now(timezone.utc)
                    et_hour = (now_utc.hour - 5) % 24
                    weekday = now_utc.weekday()

                    # Determine market status
                    if weekday >= 5:
                        market_status = "closed_weekend"
                    elif et_hour >= 4 and et_hour < 9:
                        market_status = "pre_market"
                    elif et_hour == 9 and now_utc.minute >= 30:
                        market_status = "open"
                    elif et_hour >= 10 and et_hour < 16:
                        market_status = "open"
                    elif et_hour >= 16 and et_hour < 20:
                        market_status = "after_hours"
                    else:
                        market_status = "closed"

                    # Include AI system status in heartbeat
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": now_utc.isoformat(),
                        "market_status": market_status,
                        "et_time": f"{et_hour:02d}:{now_utc.minute:02d} ET",
                        "ai_status": {
                            "active": True,
                            "scanning": True,
                            "signals_generated": signal_counter // 3,
                            "next_signal_in": f"{(3 - (signal_counter % 3)) * 30} seconds"
                        }
                    })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/momentum")
async def websocket_momentum(websocket: WebSocket):
    """High-speed WebSocket for momentum trading signals - updates every 5 seconds."""
    await manager.connect(websocket)
    momentum_tickers = ["TSLA", "NVDA", "AMD", "AAPL", "META"]
    active_positions = {}

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "⚡ Connected to High-Speed Momentum Trading",
            "timestamp": datetime.utcnow().isoformat(),
            "update_frequency": "5 seconds"
        })

        while True:
            try:
                # Check for client messages (non-blocking with short timeout)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)

                if data.startswith("track:"):
                    # Add ticker to momentum tracking
                    ticker = data.split(":")[1].upper()
                    if ticker not in momentum_tickers:
                        momentum_tickers.append(ticker)
                    await websocket.send_json({
                        "type": "tracking_added",
                        "ticker": ticker,
                        "message": f"Now tracking {ticker} for momentum"
                    })

                elif data.startswith("enter:"):
                    # Simulate position entry
                    ticker = data.split(":")[1].upper()
                    active_positions[ticker] = {
                        "entry_time": datetime.utcnow().isoformat(),
                        "entry_price": (await get_quote(ticker)).get("price", 100)
                    }
                    await websocket.send_json({
                        "type": "position_entered",
                        "ticker": ticker,
                        "entry_price": active_positions[ticker]["entry_price"]
                    })

            except asyncio.TimeoutError:
                # Send momentum updates every 5 seconds
                momentum_updates = []

                for ticker in momentum_tickers[:5]:  # Top 5 tickers for speed
                    try:
                        momentum = await get_momentum_analysis(ticker)

                        # Check if we should alert
                        should_alert = (
                            momentum["momentum_score"] >= 70 or
                            momentum["momentum_score"] <= 30 or
                            ticker in active_positions
                        )

                        if should_alert:
                            update = {
                                "ticker": ticker,
                                "score": momentum["momentum_score"],
                                "action": momentum["action"],
                                "signals": momentum["signals"][:2],
                                "flash_trade": momentum["flash_trade"],
                                "momentum_status": momentum["momentum_status"]
                            }

                            # Check position status if we have one
                            if ticker in active_positions:
                                entry_price = active_positions[ticker]["entry_price"]
                                current_price = momentum["flash_trade"]["entry_price"]
                                pnl = ((current_price - entry_price) / entry_price) * 100

                                update["position"] = {
                                    "entry": entry_price,
                                    "current": current_price,
                                    "pnl": f"{pnl:+.2f}%",
                                    "exit_signal": momentum["momentum_score"] < 45 if pnl > 0 else momentum["momentum_score"] < 35
                                }

                                # Auto-exit recommendation
                                if update["position"]["exit_signal"]:
                                    update["alert"] = "🚨 MOMENTUM LOST - CONSIDER EXIT"
                                elif pnl >= 2:
                                    update["alert"] = "🎯 TARGET HIT - TAKE PROFIT"
                                elif pnl <= -1:
                                    update["alert"] = "⛔ STOP LOSS - EXIT NOW"

                            momentum_updates.append(update)
                    except:
                        pass

                # Send consolidated update
                if momentum_updates:
                    await websocket.send_json({
                        "type": "momentum_update",
                        "updates": momentum_updates,
                        "timestamp": datetime.utcnow().isoformat(),
                        "active_positions": len(active_positions),
                        "next_update": "5 seconds"
                    })
                else:
                    # Send heartbeat if no momentum
                    await websocket.send_json({
                        "type": "heartbeat",
                        "message": "No momentum detected",
                        "timestamp": datetime.utcnow().isoformat(),
                        "scanning": momentum_tickers
                    })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    """WebSocket for real-time trade updates."""
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Trade Stream",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for client message or timeout after 30 seconds
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Handle client requests
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    # Echo for testing
                    await websocket.send_json({
                        "type": "trade_echo",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                # Send simulated trade update with more realistic prices
                # Approximate real prices as of Nov 2024
                ticker_prices = {
                    "AAPL": (220, 230),    # Apple ~$225
                    "GOOGL": (170, 180),   # Google ~$175
                    "MSFT": (485, 495),    # Microsoft ~$490
                    "TSLA": (340, 360),    # Tesla ~$350
                    "NVDA": (140, 150),    # NVIDIA ~$145
                    "META": (560, 580),    # Meta ~$570
                    "AMZN": (210, 220),    # Amazon ~$215
                }

                ticker = random.choice(list(ticker_prices.keys()))
                price_range = ticker_prices[ticker]
                base_price = random.uniform(price_range[0], price_range[1])

                # Add small random variation for realistic movement
                price_variation = random.uniform(-2, 2)
                price = round(base_price + price_variation, 2)

                # Determine action based on price movement simulation
                action = random.choice(["BUY", "SELL", "BUY", "HOLD"])  # Slightly favor BUY

                await websocket.send_json({
                    "type": "trade_update",
                    "ticker": ticker,
                    "action": action,
                    "quantity": random.randint(1, 100),
                    "price": price,
                    "timestamp": datetime.utcnow().isoformat(),
                    "note": "Simulated trade - connect to real broker for live data"
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket for system status updates."""
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to System Status",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for client message or timeout after 10 seconds for more frequent status updates
                data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)

                # Handle client requests
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    # Echo for testing
                    await websocket.send_json({
                        "type": "status_echo",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                # Send status update
                await websocket.send_json({
                    "type": "status",
                    "system": "healthy",
                    "trading_mode": settings.ALPACA_ENV,
                    "is_paper": settings.is_paper_trading,
                    "connections": len(manager.active_connections),
                    "api_status": {
                        "benzinga": benzinga_client is not None,
                        "alpaca": bool(settings.ALPACA_API_KEY_ID)
                    },
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============= DEBATE SYSTEM ENDPOINTS =============

@app.get("/api/debate/{ticker}")
async def run_debate_analysis(
    ticker: str,
    force: bool = Query(False, description="Force new debate even if cached")
):
    """
    Run a full multi-agent debate for a trading decision.

    Returns the complete debate including:
    - Initial agent positions
    - Challenges and rebuttals
    - Final weighted decision
    - Risk warnings
    """
    from app.services.debate.debate_engine import DebateEngine
    from app.services.memory.memory_store import MemoryStore
    from app.services.memory.weight_adjuster import WeightAdjuster

    ticker = ticker.upper()

    try:
        # Initialize components
        memory_store = MemoryStore()
        weight_adjuster = WeightAdjuster(memory_store)

        # Get adjusted weights
        adjusted_weights = await weight_adjuster.get_adjusted_weights()

        # Initialize debate engine with adjusted weights
        engine = DebateEngine(agent_weights=adjusted_weights)

        # Gather market data
        market_data = {"quote": {"price": 100}, "bars": [], "news": []}

        # Get quote
        if alpaca_trader:
            quote = alpaca_trader.get_quote(ticker)
            if quote:
                market_data["quote"] = {"price": quote.get("price", 100)}

        # Get news
        if benzinga_client:
            news_result = await benzinga_client.get_news(tickers=ticker, limit=10)
            market_data["news"] = news_result.get("results", [])

        # Get account and positions
        account = {"equity": 100000, "buying_power": 50000}
        positions = []
        if alpaca_trader:
            account = alpaca_trader.get_account_status() or account
            positions = alpaca_trader.get_positions() or []

        # Run debate
        outcome = await engine.run_debate(
            ticker=ticker,
            market_data=market_data,
            account=account,
            positions=positions,
        )

        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "outcome": outcome.to_dict(),
            "agent_weights": adjusted_weights,
        }

    except Exception as e:
        logger.error(f"Debate error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/similar-trades/{ticker}")
async def get_similar_trades(
    ticker: str,
    market_regime: Optional[str] = None,
    limit: int = 10,
):
    """Get similar past trades for context."""
    from app.services.memory.memory_store import MemoryStore

    try:
        store = MemoryStore()
        trades = await store.get_similar_situations(
            ticker=ticker.upper(),
            market_regime=market_regime or "neutral",
            technical_regime="neutral",
            limit=limit,
        )

        return {
            "ticker": ticker.upper(),
            "similar_trades": [t.to_dict() for t in trades],
            "count": len(trades),
        }

    except Exception as e:
        logger.error(f"Memory retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get trading memory statistics."""
    from app.services.memory.memory_store import MemoryStore

    try:
        store = MemoryStore()
        stats = await store.get_stats()
        return stats

    except Exception as e:
        logger.error(f"Memory stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/performance")
async def get_agent_performance(
    period: str = Query("month", description="day, week, month, all"),
    market_regime: Optional[str] = None,
):
    """Get performance metrics for all agents."""
    from app.services.memory.memory_store import MemoryStore

    try:
        store = MemoryStore()
        agents = ["news", "technical", "macro", "contrarian", "risk", "timing", "exit"]

        performance = {}
        for agent in agents:
            perf = await store.get_agent_accuracy(agent, period, market_regime)
            performance[agent] = perf

        return {
            "period": period,
            "market_regime": market_regime,
            "agents": performance,
        }

    except Exception as e:
        logger.error(f"Agent performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/weights")
async def get_current_weights():
    """Get current agent weights (adjusted for performance)."""
    from app.services.memory.memory_store import MemoryStore
    from app.services.memory.weight_adjuster import WeightAdjuster

    try:
        store = MemoryStore()
        adjuster = WeightAdjuster(store)

        weights = await adjuster.get_adjusted_weights()

        return {
            "weights": weights,
            "default_weights": WeightAdjuster.DEFAULT_WEIGHTS,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Weight retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/context/{ticker}")
async def get_decision_context(
    ticker: str,
    market_regime: str = "neutral",
    technical_regime: str = "neutral",
):
    """Get historical context for a trading decision."""
    from app.services.memory.memory_store import MemoryStore
    from app.services.memory.context_retriever import ContextRetriever

    try:
        store = MemoryStore()
        retriever = ContextRetriever(store)

        context = await retriever.get_decision_context(
            ticker=ticker.upper(),
            market_regime=market_regime,
            technical_regime=technical_regime,
            news_sentiment="neutral",
        )

        return {
            "ticker": ticker.upper(),
            "context": context.to_dict(),
            "formatted_prompt": retriever.format_for_prompt(context),
        }

    except Exception as e:
        logger.error(f"Context retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import asyncio

    port = int(os.getenv("PORT", "8000"))

    print(f"\n🚀 Starting AI Trading System on http://localhost:{port}")
    print(f"📚 API Documentation: http://localhost:{port}/docs")
    print(f"🔍 Health Check: http://localhost:{port}/health")
    print(f"📊 System Status: http://localhost:{port}/status")
    print(f"📰 Real News: http://localhost:{port}/api/news?ticker=AAPL")
    print(f"💹 Sentiment: http://localhost:{port}/api/sentiment/AAPL")
    print(f"🔎 Scan Core Watchlist: http://localhost:{port}/api/scan/watchlist")
    print(f"🌊 Scan Momentum Universe: http://localhost:{port}/api/scan/universe")
    print(f"🌶️  Scan Spicy High-Vol: http://localhost:{port}/api/scan/spicy\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
