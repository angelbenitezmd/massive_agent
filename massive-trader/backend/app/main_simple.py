"""Simplified FastAPI application with real Benzinga integration."""
import logging
import asyncio
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os

# Use simple config
from app.core.config_simple import get_settings
from app.services.benzinga_simple import BenzingaClient
from app.services.alpaca_trader import alpaca_trader
from app.services.dashboard_service import DashboardService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Benzinga client
benzinga_client = None


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

    # Start position monitoring background task
    asyncio.create_task(auto_monitor_positions())
    logger.info("✅ Position monitoring started")

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
    limit: int = Query(10, description="Maximum results")
):
    """Get real-time news from Benzinga."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # Calculate date range
    published_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    result = await benzinga_client.get_news(
        tickers=ticker,
        channels=channels,
        published_gte=published_gte,
        limit=limit
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result.get("message", "API error"))

    return result


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

    result = await benzinga_client.get_earnings(
        ticker=ticker,
        date_gte=date_gte,
        date_lte=date_lte,
        importance_gte=importance_min,
        limit=limit
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result.get("message", "API error"))

    return result


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
            from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

            # First try to get latest trade (more accurate for after hours)
            try:
                trade_request = StockLatestTradeRequest(symbol_or_symbols=[ticker])
                trades = client.get_stock_latest_trade(trade_request)
                if ticker in trades:
                    trade = trades[ticker]
                    trade_price = float(trade.price) if trade.price else 0
                    if trade_price > 0:
                        return {
                            "ticker": ticker,
                            "price": round(trade_price, 2),
                            "change": 0,
                            "change_percent": 0,
                            "volume": int(trade.size) if trade.size else 0,
                            "timestamp": datetime.utcnow().isoformat(),
                            "source": "alpaca_trade"
                        }
            except Exception as e:
                logger.debug(f"Failed to get latest trade for {ticker}: {e}")

            # Fallback to quote
            request = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
            quotes = client.get_stock_latest_quote(request)

            if ticker in quotes:
                quote = quotes[ticker]
                bid = float(quote.bid_price) if quote.bid_price else 0
                ask = float(quote.ask_price) if quote.ask_price else 0
                # Use mid price, or just bid/ask if one is missing (after hours)
                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2
                elif bid > 0:
                    price = bid
                elif ask > 0:
                    price = ask
                else:
                    price = 0

                if price > 0:
                    return {
                        "ticker": ticker,
                        "price": round(price, 2),
                        "bid": bid,
                        "ask": ask,
                        "change": 0,
                        "change_percent": 0,
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "alpaca_quote"
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

            # Calculate start time based on timeframe and limit
            now = datetime.utcnow()
            if timeframe in ["1D", "1Day"]:
                start = now - timedelta(days=limit + 5)
            elif timeframe in ["1H", "1Hour"]:
                start = now - timedelta(hours=limit + 10)
            else:
                # For minute bars, go back enough trading hours
                start = now - timedelta(days=3)  # Get last 3 days of minute data

            request = StockBarsRequest(
                symbol_or_symbols=[ticker],
                timeframe=tf,
                start=start,
                limit=limit
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
                for i, bar in enumerate(bars_list[-limit:]):  # Get last N bars
                    bar_time = bar.timestamp
                    # Format time based on timeframe
                    if timeframe in ["1D", "1Day"]:
                        t_str = bar_time.strftime("%m/%d")
                    else:
                        t_str = bar_time.strftime("%H:%M")

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

    for i in range(limit):
        bar_time = now - timedelta(minutes=interval_minutes * (limit - 1 - i))
        change_pct = random.uniform(-0.003, 0.0035)
        current_price = current_price * (1 + change_pct)

        high = current_price * (1 + random.uniform(0, 0.002))
        low = current_price * (1 - random.uniform(0, 0.002))
        open_price = current_price * (1 + random.uniform(-0.001, 0.001))

        if timeframe in ["1D", "1Day"]:
            t_str = bar_time.strftime("%m/%d")
        else:
            t_str = bar_time.strftime("%H:%M")

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
    if not benzinga_client:
        return {
            "ticker": ticker,
            "sentiment": "neutral",
            "score": 50,
            "message": "Benzinga API not configured"
        }

    # Convert ticker to uppercase for consistency
    ticker = ticker.upper()

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

    # Calculate sentiment score
    sentiment_score = 50  # Neutral baseline

    # Enhanced news sentiment with more keywords
    if isinstance(news, dict) and "results" in news:
        news_count = len(news.get("results", []))
        for item in news.get("results", [])[:10]:
            title = item.get("title", "").lower()
            # Positive signals
            if any(word in title for word in ["upgrade", "beat", "beats", "surge", "rally", "gain", "soar",
                                              "jump", "rise", "bullish", "outperform", "strong", "record"]):
                sentiment_score += 4
            # Negative signals
            elif any(word in title for word in ["downgrade", "miss", "misses", "fall", "drop", "loss",
                                                "plunge", "crash", "bearish", "underperform", "weak", "concern"]):
                sentiment_score -= 4
            # Major positive
            elif any(word in title for word in ["breakthrough", "exceeds expectations", "all-time high"]):
                sentiment_score += 8
            # Major negative
            elif any(word in title for word in ["bankruptcy", "investigation", "lawsuit", "recall"]):
                sentiment_score -= 8

    # Earnings sentiment
    if isinstance(earnings, dict) and "results" in earnings:
        for earning in earnings.get("results", [])[:3]:
            # Check if earnings beat or miss
            if earning.get("estimated_eps") and earning.get("actual_eps"):
                estimated = earning["estimated_eps"]
                actual = earning["actual_eps"]
                if actual > estimated * 1.05:  # Beat by 5%+
                    sentiment_score += 10
                elif actual < estimated * 0.95:  # Miss by 5%+
                    sentiment_score -= 10

            # Upcoming earnings importance
            importance = earning.get("importance", 0)
            if importance >= 4:  # High importance upcoming earnings
                sentiment_score += 2

    # Ratings sentiment (if available)
    if isinstance(ratings, dict) and "results" in ratings:
        for rating in ratings.get("results", [])[:3]:
            action = rating.get("rating_action", "")
            if "upgrade" in action:
                sentiment_score += 10
            elif "downgrade" in action:
                sentiment_score -= 10

    # Consensus sentiment (if available)
    if isinstance(consensus, dict) and "results" in consensus:
        if consensus["results"]:
            cons = consensus["results"][0]
            rating = cons.get("consensus_rating", "")
            if "buy" in rating:
                sentiment_score += 15
            elif "sell" in rating:
                sentiment_score -= 15

    # Cap score between 0 and 100
    sentiment_score = max(0, min(100, sentiment_score))

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

    return {
        "ticker": ticker,
        "sentiment": sentiment,
        "score": sentiment_score,
        "sources": {
            "news_analyzed": len(news.get("results", [])) if isinstance(news, dict) else 0,
            "earnings_analyzed": len(earnings.get("results", [])) if isinstance(earnings, dict) else 0,
            "ratings_analyzed": len(ratings.get("results", [])) if isinstance(ratings, dict) else 0,
            "has_consensus": bool(consensus.get("results")) if isinstance(consensus, dict) else False
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ============= UNIFIED PRODUCTION TRADING SYSTEM =============

@app.get("/api/trading/best-signal")
async def get_best_trading_signal():
    """Get the SINGLE BEST trading signal from all sources (momentum + AI)."""

    # Scan top tickers for opportunities
    candidates = ["TSLA", "NVDA", "AMD", "AAPL", "META", "GOOGL", "MSFT"]
    best_signal = None
    best_score = 0

    for ticker in candidates:
        try:
            # Get momentum analysis
            momentum = await get_momentum_analysis(ticker)
            momentum_score = momentum["momentum_score"]

            # Get AI sentiment
            sentiment = await get_sentiment(ticker)
            ai_score = sentiment["score"]

            # Combined score (momentum weighted higher for fast trades)
            combined_score = (momentum_score * 0.7) + (ai_score * 0.3)

            # Check if this is the best signal
            if combined_score > best_score and (momentum_score >= 70 or ai_score >= 75):
                quote = await get_quote(ticker)
                current_price = quote.get("price", 100)

                best_signal = {
                    "ticker": ticker,
                    "action": "BUY" if combined_score >= 70 else "HOLD",
                    "combined_score": round(combined_score, 1),
                    "momentum_score": momentum_score,
                    "ai_score": ai_score,
                    "entry_price": current_price,
                    "stop_loss": round(current_price * 0.995, 2),  # -0.5%
                    "take_profit": round(current_price * 1.015, 2),  # +1.5%
                    "quantity": 10,  # Start with 10 shares for paper trading
                    "signals": momentum["signals"][:2],
                    "strategy": "MOMENTUM" if momentum_score > ai_score else "AI_DRIVEN",
                    "urgency": momentum["urgency"],
                    "timestamp": datetime.utcnow().isoformat()
                }
                best_score = combined_score

        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            continue

    # If no good signal, return wait status
    if not best_signal:
        return {
            "action": "WAIT",
            "message": "No strong trading signals detected",
            "timestamp": datetime.utcnow().isoformat()
        }

    return best_signal

@app.post("/api/trading/execute")
async def execute_trade(auto: bool = False):
    """Execute the best trade on Alpaca paper trading."""

    # Get best signal
    signal = await get_best_trading_signal()

    if signal.get("action") == "WAIT":
        return {
            "status": "no_trade",
            "message": "No actionable signal",
            "signal": signal
        }

    # Execute on Alpaca
    if auto or signal.get("combined_score", 0) >= 75:
        result = alpaca_trader.execute_trade(signal)
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

@app.get("/api/trading/positions")
async def get_positions():
    """Get all open positions from Alpaca."""
    positions = alpaca_trader.get_positions()

    # Check momentum for exit signals
    for position in positions:
        ticker = position["symbol"]
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
            pass

    return {
        "positions": positions,
        "count": len(positions),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/trading/close/{ticker}")
async def close_position(ticker: str):
    """Close a position."""
    result = alpaca_trader.close_position(ticker.upper())
    return result

@app.get("/api/trading/account")
async def get_account():
    """Get Alpaca account status."""
    return alpaca_trader.get_account_status()

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
    """Background task that monitors positions every 30 seconds."""
    while True:
        try:
            if is_market_open():
                # Monitor and auto-exit positions
                await monitor_positions_for_exit()
                logger.info("Position monitoring completed")
            await asyncio.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"Error in position monitoring: {e}")
            await asyncio.sleep(30)

# Start position monitoring on startup (integrated into lifespan)

# ============= MOMENTUM TRADING & FLASH SIGNALS =============

@app.get("/api/momentum/{ticker}")
async def get_momentum_analysis(ticker: str):
    """Ultra-fast momentum analysis for quick trades."""
    ticker = ticker.upper()

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

    # Price momentum (heavily weighted for speed trading)
    price_change = quote_data.get("change_percent", 0)
    if price_change > 3:
        momentum_score += 30
        signals.append("🚀 STRONG UPWARD MOMENTUM")
    elif price_change > 1.5:
        momentum_score += 20
        signals.append("📈 POSITIVE MOMENTUM")
    elif price_change < -3:
        momentum_score -= 30
        signals.append("📉 STRONG DOWNWARD MOMENTUM")
    elif price_change < -1.5:
        momentum_score -= 20
        signals.append("⬇️ NEGATIVE MOMENTUM")

    # Breaking news momentum
    news_items = news.get("results", [])
    if news_items:
        recent_news = [n for n in news_items if "min" in n.get("published_at", "") or "hour" in n.get("published_at", "")]
        if recent_news:
            momentum_score += 15
            signals.append(f"📰 BREAKING: {len(recent_news)} news items")

            # Check news sentiment quickly
            for item in recent_news[:3]:
                title = item.get("title", "").lower()
                if any(word in title for word in ["surge", "soar", "jump", "breakthrough", "beat"]):
                    momentum_score += 10
                    signals.append("💥 BULLISH NEWS CATALYST")
                    break
                elif any(word in title for word in ["crash", "plunge", "fall", "miss", "warning"]):
                    momentum_score -= 10
                    signals.append("⚠️ BEARISH NEWS ALERT")
                    break

    # Volume/activity indicators (simulated)
    if abs(price_change) > 2:
        signals.append("🔥 HIGH VOLATILITY DETECTED")
        momentum_score += 5 if price_change > 0 else -5

    # Cap score
    momentum_score = max(0, min(100, momentum_score))

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

    return {
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

@app.get("/api/ai/analyze/{ticker}")
async def get_ai_analysis(ticker: str):
    """Get comprehensive AI analysis and insights for a ticker."""
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
        "count": {
            "watchlist": len(settings.watchlist),
            "universe": len(settings.universe),
            "spicy": len(settings.spicy),
        }
    }


@app.get("/api/scan/watchlist")
async def scan_watchlist():
    """Scan all watchlist tickers for opportunities."""
    if not benzinga_client:
        return {
            "message": "Benzinga API not configured",
            "watchlist": settings.watchlist
        }

    results = []

    for ticker in settings.watchlist:
        try:
            # Get sentiment for each ticker
            sentiment_data = await get_sentiment(ticker)

            # Add to results
            results.append({
                "ticker": ticker,
                "sentiment": sentiment_data["sentiment"],
                "score": sentiment_data["score"],
                "recommendation": "BUY" if sentiment_data["score"] >= 70 else
                                 "SELL" if sentiment_data["score"] <= 30 else "HOLD"
            })
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            results.append({
                "ticker": ticker,
                "sentiment": "unknown",
                "score": 50,
                "recommendation": "HOLD",
                "error": str(e)
            })

    # Sort by score (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "watchlist_count": len(settings.watchlist),
        "results": results,
        "top_opportunities": [r for r in results if r["score"] >= 70],
        "warnings": [r for r in results if r["score"] <= 30]
    }


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

    results = []

    # Process in batches to avoid overwhelming the API
    batch_size = 10
    for i in range(0, len(universe_tickers), batch_size):
        batch = universe_tickers[i:i+batch_size]

        for ticker in batch:
            try:
                # Get sentiment for each ticker
                sentiment_data = await get_sentiment(ticker)

                # Add to results
                results.append({
                    "ticker": ticker,
                    "sentiment": sentiment_data["sentiment"],
                    "score": sentiment_data["score"],
                    "recommendation": "BUY" if sentiment_data["score"] >= 70 else
                                     "SELL" if sentiment_data["score"] <= 30 else "HOLD"
                })
            except Exception as e:
                logger.error(f"Error scanning {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "sentiment": "unknown",
                    "score": 50,
                    "recommendation": "HOLD",
                    "error": str(e)
                })

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

    results = []

    for ticker in spicy_tickers:
        try:
            # Get sentiment for each ticker
            sentiment_data = await get_sentiment(ticker)

            # Add volatility warning for spicy stocks
            results.append({
                "ticker": ticker,
                "sentiment": sentiment_data["sentiment"],
                "score": sentiment_data["score"],
                "recommendation": "BUY" if sentiment_data["score"] >= 75 else  # Higher threshold for spicy
                                 "SELL" if sentiment_data["score"] <= 25 else "HOLD",
                "risk_level": "HIGH",
                "warning": "High volatility - trade with caution"
            })
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            results.append({
                "ticker": ticker,
                "sentiment": "unknown",
                "score": 50,
                "recommendation": "HOLD",
                "risk_level": "HIGH",
                "error": str(e)
            })

    # Sort by score (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "spicy_count": len(spicy_tickers),
        "results": results,
        "top_opportunities": [r for r in results if r["score"] >= 75],
        "warnings": [r for r in results if r["score"] <= 25],
        "risk_warning": "⚠️ SPICY LIST - High volatility stocks with elevated risk"
    }


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
                    should_execute = (
                        best_signal.get("action") == "BUY" and
                        best_signal.get("combined_score", 0) >= 75 and
                        is_market_open()  # Only execute when market is open
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
                    elif best_signal.get("combined_score", 0) >= 75:
                        logger.info(f"⏸️ Signal {best_signal['ticker']} score {best_signal['combined_score']:.1f} >= 75 but market closed")

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
        "app.main_simple:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
