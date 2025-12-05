"""
Main Trading Loop with Smart LLM Usage.

Key principle: LLMs are the expensive "brain", not the heartbeat.
The heartbeat every minute should be mostly cheap (Alpaca + indicators + scanner).
LLMs should only run when there is new information or a strong reason.

This module implements the 1-minute loop that:
1. ALWAYS: Updates Alpaca quotes, recalculates local indicators, updates scanner
2. SELECTIVELY: Calls LLM agents only when data changes warrant it
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from app.services.agent_cache import agent_cache, AgentType
from app.services.technical_indicators import (
    analyze_technical,
    calculate_scanner_score,
    TechnicalSignal,
)
from app.services.ai_agents import (
    run_full_analysis,
    run_quick_analysis,
    get_cache_status,
)

logger = logging.getLogger(__name__)


@dataclass
class TickerState:
    """Tracks state for a single ticker."""
    ticker: str
    last_quote_price: float = 0.0
    last_quote_time: Optional[datetime] = None

    # Technical state (updated every loop)
    technical_signal: Optional[TechnicalSignal] = None
    scanner_score: float = 50.0

    # Benzinga data timestamps (for change detection)
    last_news_ts: Optional[datetime] = None
    last_earnings_ts: Optional[datetime] = None
    last_rating_ts: Optional[datetime] = None

    # LLM agent results (cached)
    last_full_analysis: Optional[Dict] = None
    last_full_analysis_time: Optional[datetime] = None

    # Loop counters
    loops_since_llm: int = 0


@dataclass
class LoopState:
    """Global state for the trading loop."""
    tickers: Dict[str, TickerState] = field(default_factory=dict)
    loop_count: int = 0
    last_loop_time: Optional[datetime] = None

    # Config
    loop_interval_seconds: int = 60
    llm_check_interval_loops: int = 1  # Check LLM conditions every loop
    deep_analysis_interval_loops: int = 5  # Force deep analysis every 5 loops

    # Risk state
    circuit_breaker_level: int = 0  # 0=normal, 1=caution, 2=halt
    daily_pnl: float = 0.0
    max_drawdown: float = 0.0

    def get_ticker_state(self, ticker: str) -> TickerState:
        """Get or create state for a ticker."""
        ticker = ticker.upper()
        if ticker not in self.tickers:
            self.tickers[ticker] = TickerState(ticker=ticker)
        return self.tickers[ticker]


class TradingLoop:
    """
    Main trading loop with smart LLM usage.

    Runs every 60 seconds during market hours.
    Cheap operations every loop, LLM calls only when needed.
    """

    def __init__(
        self,
        watchlist: List[str],
        benzinga_client=None,
        alpaca_trader=None,
        loop_interval: int = 60,
    ):
        """
        Initialize trading loop.

        Args:
            watchlist: List of tickers to monitor
            benzinga_client: Benzinga API client
            alpaca_trader: Alpaca trading client
            loop_interval: Seconds between loops (default 60)
        """
        self.watchlist = [t.upper() for t in watchlist]
        self.benzinga_client = benzinga_client
        self.alpaca_trader = alpaca_trader

        self.state = LoopState(loop_interval_seconds=loop_interval)
        self._running = False

        logger.info(
            f"TradingLoop initialized with {len(watchlist)} tickers, "
            f"{loop_interval}s interval"
        )

    async def start(self):
        """Start the trading loop."""
        self._running = True
        logger.info("Starting trading loop...")

        while self._running:
            try:
                await self._run_loop_iteration()
            except Exception as e:
                logger.error(f"Loop iteration error: {e}", exc_info=True)

            # Wait for next interval
            await asyncio.sleep(self.state.loop_interval_seconds)

    def stop(self):
        """Stop the trading loop."""
        self._running = False
        logger.info("Stopping trading loop...")

    async def _run_loop_iteration(self):
        """
        Run one iteration of the trading loop.

        This is called every 60 seconds. It performs:
        1. CHEAP operations (always): Quotes, local indicators, scanner
        2. CONDITIONAL operations: LLM agents only when data changed
        """
        loop_start = datetime.utcnow()
        self.state.loop_count += 1
        self.state.last_loop_time = loop_start

        logger.info(f"=== Loop {self.state.loop_count} starting ===")

        # Track what we did this loop
        loop_summary = {
            "loop": self.state.loop_count,
            "tickers_processed": 0,
            "quotes_updated": 0,
            "technical_calculated": 0,
            "llm_calls_made": 0,
            "llm_calls_skipped": 0,
            "cache_hits": 0,
        }

        # Process each ticker
        for ticker in self.watchlist:
            try:
                ticker_result = await self._process_ticker(ticker)
                loop_summary["tickers_processed"] += 1

                if ticker_result.get("quote_updated"):
                    loop_summary["quotes_updated"] += 1
                if ticker_result.get("technical_calculated"):
                    loop_summary["technical_calculated"] += 1
                if ticker_result.get("llm_called"):
                    loop_summary["llm_calls_made"] += 1
                if ticker_result.get("llm_skipped"):
                    loop_summary["llm_calls_skipped"] += 1
                if ticker_result.get("cache_hit"):
                    loop_summary["cache_hits"] += 1

            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")

        # Update risk state
        await self._update_risk_state()

        # Log summary
        loop_duration = (datetime.utcnow() - loop_start).total_seconds()
        loop_summary["duration_seconds"] = round(loop_duration, 2)

        logger.info(
            f"Loop {self.state.loop_count} complete in {loop_duration:.1f}s: "
            f"{loop_summary['llm_calls_made']} LLM calls, "
            f"{loop_summary['llm_calls_skipped']} skipped, "
            f"{loop_summary['cache_hits']} cache hits"
        )

        return loop_summary

    async def _process_ticker(self, ticker: str) -> Dict[str, Any]:
        """
        Process a single ticker in the loop.

        Always does:
        - Update quote from Alpaca
        - Calculate local technical indicators
        - Update scanner score

        Conditionally does:
        - Check Benzinga for new news/earnings/ratings
        - Run LLM agents if data changed
        """
        ticker = ticker.upper()
        ticker_state = self.state.get_ticker_state(ticker)
        result = {
            "ticker": ticker,
            "quote_updated": False,
            "technical_calculated": False,
            "llm_called": False,
            "llm_skipped": False,
            "cache_hit": False,
        }

        # 1. ALWAYS: Get current quote from Alpaca
        quote = await self._get_quote(ticker)
        if quote:
            ticker_state.last_quote_price = quote.get("price", 0)
            ticker_state.last_quote_time = datetime.utcnow()
            result["quote_updated"] = True

        # 2. ALWAYS: Get bars and calculate local technical indicators
        bars = await self._get_bars(ticker)
        if bars:
            ticker_state.technical_signal = analyze_technical(
                ticker, ticker_state.last_quote_price, bars
            )
            result["technical_calculated"] = True

        # 3. ALWAYS: Update scanner score (no LLM)
        momentum_score = await self._get_momentum_score(ticker)
        sentiment_score = await self._get_simple_sentiment_score(ticker)

        if ticker_state.technical_signal:
            ticker_state.scanner_score = calculate_scanner_score(
                ticker_state.technical_signal,
                momentum_score,
                sentiment_score,
            )

        # 4. CONDITIONAL: Check if we need LLM analysis
        should_run_llm = await self._should_run_llm_analysis(ticker, ticker_state)

        if should_run_llm:
            # Run full LLM analysis (with internal caching)
            logger.info(f"{ticker}: Running LLM analysis...")
            ticker_state.loops_since_llm = 0

            analysis = await self._run_llm_analysis(ticker, ticker_state, bars)

            if analysis:
                ticker_state.last_full_analysis = analysis
                ticker_state.last_full_analysis_time = datetime.utcnow()

                if analysis.get("cached_agents", {}).get("news"):
                    result["cache_hit"] = True
                else:
                    result["llm_called"] = True
        else:
            logger.debug(f"{ticker}: Skipping LLM analysis (no change detected)")
            ticker_state.loops_since_llm += 1
            result["llm_skipped"] = True

        return result

    async def _should_run_llm_analysis(
        self,
        ticker: str,
        ticker_state: TickerState,
    ) -> bool:
        """
        Determine if LLM analysis should run for this ticker.

        Returns True if:
        - No previous analysis exists
        - New news arrived since last analysis
        - Within earnings window
        - Technical regime changed significantly
        - Forced by interval (every N loops)
        """
        # No previous analysis
        if ticker_state.last_full_analysis is None:
            logger.info(f"{ticker}: No prior analysis, will run LLM")
            return True

        # Force periodic refresh
        if ticker_state.loops_since_llm >= self.state.deep_analysis_interval_loops:
            logger.info(
                f"{ticker}: Forced refresh after {ticker_state.loops_since_llm} loops"
            )
            return True

        # Check for new Benzinga data
        new_data = await self._check_for_new_benzinga_data(ticker, ticker_state)
        if new_data.get("has_new_news"):
            logger.info(f"{ticker}: New news detected, will run LLM")
            return True
        if new_data.get("has_new_earnings"):
            logger.info(f"{ticker}: New earnings data, will run LLM")
            return True
        if new_data.get("has_new_ratings"):
            logger.info(f"{ticker}: New analyst rating, will run LLM")
            return True

        # Check for technical regime change
        if ticker_state.technical_signal:
            last_analysis = ticker_state.last_full_analysis or {}
            last_tech = last_analysis.get("agents", {}).get("technical", {})
            last_score = last_tech.get("score", 50)
            current_score = ticker_state.technical_signal.score

            # Significant score change (>15 points)
            if abs(current_score - last_score) > 15:
                logger.info(
                    f"{ticker}: Technical score changed significantly "
                    f"({last_score:.0f} -> {current_score:.0f}), will run LLM"
                )
                return True

        return False

    async def _check_for_new_benzinga_data(
        self,
        ticker: str,
        ticker_state: TickerState,
    ) -> Dict[str, bool]:
        """Check Benzinga for new data since last check."""
        result = {
            "has_new_news": False,
            "has_new_earnings": False,
            "has_new_ratings": False,
        }

        if not self.benzinga_client:
            return result

        try:
            # Check for new news (today)
            news = await self.benzinga_client.get_news(
                tickers=ticker,
                published_gte=(datetime.utcnow() - timedelta(days=1)).strftime(
                    "%Y-%m-%d"
                ),
                limit=5,
            )
            if news.get("results"):
                # Get timestamp of newest article
                newest = news["results"][0]
                newest_ts_str = newest.get("created", newest.get("published_at", ""))
                if newest_ts_str:
                    try:
                        newest_ts = datetime.fromisoformat(
                            newest_ts_str.replace("Z", "+00:00")
                        )
                        if (
                            ticker_state.last_news_ts is None
                            or newest_ts > ticker_state.last_news_ts
                        ):
                            result["has_new_news"] = True
                            ticker_state.last_news_ts = newest_ts
                    except ValueError:
                        pass

            # Check for new earnings (less frequently)
            if ticker_state.loops_since_llm >= 3:  # Every 3 loops
                earnings = await self.benzinga_client.get_earnings(
                    ticker=ticker,
                    limit=1,
                )
                if earnings.get("results"):
                    earnings_event = earnings["results"][0]
                    # Check if this is a new event
                    report_date = earnings_event.get("report_date")
                    if report_date:
                        # Check if we're in the earnings window
                        try:
                            report_dt = datetime.strptime(report_date, "%Y-%m-%d")
                            days_away = abs((report_dt - datetime.utcnow()).days)
                            if days_away <= 1:  # Within 1 day of earnings
                                result["has_new_earnings"] = True
                        except ValueError:
                            pass

            # Check for new ratings (every 5 loops - they change rarely)
            if ticker_state.loops_since_llm >= 5:
                ratings = await self.benzinga_client.get_ratings(
                    ticker=ticker,
                    limit=1,
                )
                if ratings.get("results"):
                    rating = ratings["results"][0]
                    rating_date = rating.get("date", rating.get("created", ""))
                    if rating_date:
                        try:
                            rating_ts = datetime.fromisoformat(
                                rating_date.replace("Z", "+00:00")
                            )
                            if (
                                ticker_state.last_rating_ts is None
                                or rating_ts > ticker_state.last_rating_ts
                            ):
                                result["has_new_ratings"] = True
                                ticker_state.last_rating_ts = rating_ts
                        except ValueError:
                            pass

        except Exception as e:
            logger.warning(f"Error checking Benzinga data for {ticker}: {e}")

        return result

    async def _run_llm_analysis(
        self,
        ticker: str,
        ticker_state: TickerState,
        bars: List[Dict],
    ) -> Optional[Dict]:
        """Run full LLM analysis for a ticker."""
        if not self.benzinga_client:
            # Fall back to quick analysis if no Benzinga
            return await run_quick_analysis(
                ticker, ticker_state.last_quote_price, bars
            )

        try:
            # Gather data for LLM analysis
            news = await self.benzinga_client.get_news(tickers=ticker, limit=10)
            news_items = news.get("results", [])

            earnings = await self.benzinga_client.get_earnings(ticker=ticker, limit=3)
            earnings_data = (
                earnings.get("results", [{}])[0]
                if earnings.get("results")
                else None
            )

            # Get account/positions if available
            account = None
            positions = None
            if self.alpaca_trader:
                account = self.alpaca_trader.get_account_status()
                positions = self.alpaca_trader.get_positions()

            # Get risk state for consensus cache check
            risk_state = {
                "circuit_breaker": self.state.circuit_breaker_level,
                "daily_pnl": self.state.daily_pnl,
            }

            # Run full analysis with caching
            result = await run_full_analysis(
                ticker=ticker,
                news_items=news_items,
                current_price=ticker_state.last_quote_price,
                bars=bars,
                rsi=ticker_state.technical_signal.rsi if ticker_state.technical_signal else None,
                macd={
                    "value": ticker_state.technical_signal.macd_value,
                    "signal": ticker_state.technical_signal.macd_signal,
                    "histogram": ticker_state.technical_signal.macd_histogram,
                } if ticker_state.technical_signal else None,
                sma_20=ticker_state.technical_signal.sma_20 if ticker_state.technical_signal else None,
                sma_50=ticker_state.technical_signal.sma_50 if ticker_state.technical_signal else None,
                earnings=earnings_data,
                account=account,
                positions=positions,
                latest_news_ts=ticker_state.last_news_ts,
                risk_state=risk_state,
            )

            return result

        except Exception as e:
            logger.error(f"LLM analysis error for {ticker}: {e}")
            return None

    async def _get_quote(self, ticker: str) -> Optional[Dict]:
        """Get current quote from Alpaca (placeholder - integrate with main_simple)."""
        # This would integrate with the existing get_quote function
        # For now, return None to indicate integration needed
        return None

    async def _get_bars(self, ticker: str) -> List[Dict]:
        """Get price bars from Alpaca (placeholder - integrate with main_simple)."""
        # This would integrate with the existing get_bars function
        return []

    async def _get_momentum_score(self, ticker: str) -> float:
        """Get simple momentum score (no LLM)."""
        ticker_state = self.state.get_ticker_state(ticker)
        if ticker_state.technical_signal:
            # Use technical score as momentum proxy
            return ticker_state.technical_signal.score
        return 50.0

    async def _get_simple_sentiment_score(self, ticker: str) -> float:
        """
        Get simple sentiment score without LLM.

        Uses keyword matching on recent news (cheap operation).
        """
        if not self.benzinga_client:
            return 50.0

        try:
            news = await self.benzinga_client.get_news(
                tickers=ticker,
                published_gte=(datetime.utcnow() - timedelta(days=1)).strftime(
                    "%Y-%m-%d"
                ),
                limit=10,
            )

            score = 50.0
            for item in news.get("results", [])[:5]:
                title = item.get("title", "").lower()
                # Simple keyword matching
                if any(w in title for w in ["surge", "soar", "beat", "upgrade", "bullish"]):
                    score += 5
                elif any(w in title for w in ["crash", "plunge", "miss", "downgrade", "bearish"]):
                    score -= 5

            return max(0, min(100, score))

        except Exception:
            return 50.0

    async def _update_risk_state(self):
        """Update global risk state."""
        if not self.alpaca_trader:
            return

        try:
            account = self.alpaca_trader.get_account_status()
            # Update daily P&L tracking
            # This is a placeholder - would need proper implementation
            pass
        except Exception as e:
            logger.warning(f"Error updating risk state: {e}")

    def get_loop_status(self) -> Dict[str, Any]:
        """Get current loop status for monitoring."""
        cache_stats = get_cache_status()

        return {
            "running": self._running,
            "loop_count": self.state.loop_count,
            "last_loop_time": (
                self.state.last_loop_time.isoformat()
                if self.state.last_loop_time
                else None
            ),
            "interval_seconds": self.state.loop_interval_seconds,
            "watchlist": self.watchlist,
            "ticker_states": {
                ticker: {
                    "last_price": state.last_quote_price,
                    "scanner_score": state.scanner_score,
                    "loops_since_llm": state.loops_since_llm,
                    "has_full_analysis": state.last_full_analysis is not None,
                    "technical_regime": (
                        state.technical_signal.regime.value
                        if state.technical_signal
                        else None
                    ),
                }
                for ticker, state in self.state.tickers.items()
            },
            "risk_state": {
                "circuit_breaker": self.state.circuit_breaker_level,
                "daily_pnl": self.state.daily_pnl,
            },
            "cache_stats": cache_stats,
        }


# Singleton instance (to be initialized with dependencies)
trading_loop: Optional[TradingLoop] = None


def get_trading_loop() -> Optional[TradingLoop]:
    """Get the global trading loop instance."""
    return trading_loop


def init_trading_loop(
    watchlist: List[str],
    benzinga_client=None,
    alpaca_trader=None,
    loop_interval: int = 60,
) -> TradingLoop:
    """Initialize the global trading loop."""
    global trading_loop
    trading_loop = TradingLoop(
        watchlist=watchlist,
        benzinga_client=benzinga_client,
        alpaca_trader=alpaca_trader,
        loop_interval=loop_interval,
    )
    return trading_loop
