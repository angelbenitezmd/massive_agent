"""Hybrid orchestrator for event-driven and interval-based trading."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from app.core.config import get_settings
from app.models.signals import StrategySignal, MarketEvent, AgentScore
from app.models.trading import TradeOrder
from app.services.benzinga_client import BenzingaClient
from app.services.alpaca_client import AlpacaClient
from app.services.risk_engine import RiskEngine
from app.services.ai_agents import (
    run_full_analysis,
    run_quick_analysis,
    NewsIntelligenceAgent,
    TechnicalAnalysisAgent,
    SentimentSynthesisAgent,
)

logger = logging.getLogger(__name__)


class HybridOrchestrator:
    """Orchestrate hybrid trading with event and interval modes."""

    def __init__(self):
        """Initialize the orchestrator."""
        self.settings = get_settings()
        self.interval_seconds = self.settings.TRADING_HYBRID_INTERVAL_SECONDS
        self.watchlist = self.settings.watchlist

        # Initialize clients
        self.benzinga = BenzingaClient()
        self.alpaca = AlpacaClient()
        self.risk_engine = RiskEngine()

        # Track last check times
        self.last_news_check = {}
        self.last_earnings_check = datetime.utcnow() - timedelta(hours=1)
        self.last_ratings_check = datetime.utcnow() - timedelta(hours=1)

        # Signal queue
        self.signal_queue: List[StrategySignal] = []

        logger.info(f"Initialized HybridOrchestrator with {len(self.watchlist)} tickers")
        logger.info(f"Interval: {self.interval_seconds}s")

    async def start(self):
        """Start the hybrid orchestrator."""
        logger.info("Starting Hybrid Orchestrator...")
        logger.info(f"Trading Mode: {self.settings.ALPACA_ENV}")

        if self.settings.ALPACA_ENV == "live":
            logger.warning("⚠️ LIVE TRADING ACTIVE - REAL MONEY AT RISK ⚠️")

        # Start both event and interval loops
        await asyncio.gather(
            self.event_loop(),
            self.interval_loop(),
            return_exceptions=True
        )

    async def event_loop(self):
        """Event-driven loop for real-time market events."""
        logger.info("Starting event-driven loop...")

        while True:
            try:
                # Check for breaking news
                await self.check_breaking_news()

                # Check for new ratings
                await self.check_new_ratings()

                # Check for earnings surprises
                await self.check_earnings_events()

                # Short delay between event checks
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error in event loop: {e}")
                await asyncio.sleep(30)

    async def interval_loop(self):
        """Interval-based loop for systematic analysis."""
        logger.info(f"Starting interval loop ({self.interval_seconds}s)...")

        while True:
            try:
                # Run comprehensive analysis on watchlist
                signals = await self.run_interval_cycle()

                # Process any generated signals
                for signal in signals:
                    await self.process_signal(signal)

                # Wait for next interval
                await asyncio.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"Error in interval loop: {e}")
                await asyncio.sleep(self.interval_seconds)

    async def check_breaking_news(self):
        """Check for breaking news on watchlist."""
        for ticker in self.watchlist:
            try:
                # Check if we've looked recently
                last_check = self.last_news_check.get(ticker, datetime.utcnow() - timedelta(hours=1))
                if datetime.utcnow() - last_check < timedelta(minutes=5):
                    continue

                # Fetch recent news
                news_response = await self.benzinga.get_news(
                    tickers=ticker,
                    published_gte=(datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d"),
                    limit=10
                )

                self.last_news_check[ticker] = datetime.utcnow()

                if not news_response.results:
                    continue

                # Check for urgent news
                for news in news_response.results:
                    age = datetime.utcnow() - news.published
                    if age.total_seconds() < 300:  # Less than 5 minutes old
                        logger.info(f"BREAKING NEWS for {ticker}: {news.title}")

                        # Create market event
                        event = MarketEvent(
                            event_type="news",
                            ticker=ticker,
                            source_id=str(news.benzinga_id),
                            urgency=0.9,
                            data={"news": news.dict()}
                        )

                        # Generate signal
                        signal = await self.run_event_driven(event)
                        if signal:
                            await self.process_signal(signal)

            except Exception as e:
                logger.error(f"Error checking news for {ticker}: {e}")

    async def check_new_ratings(self):
        """Check for new analyst ratings."""
        try:
            # Fetch recent ratings
            ratings_response = await self.benzinga.get_ratings(
                ticker_any_of=self.watchlist,
                date_gte=self.last_ratings_check.strftime("%Y-%m-%d"),
                limit=20,
                sort="date.desc"
            )

            self.last_ratings_check = datetime.utcnow()

            for rating in ratings_response.results:
                # Check if it's an upgrade or downgrade
                if rating.rating_action in ["upgrades", "downgrades"]:
                    logger.info(f"RATING CHANGE for {rating.ticker}: {rating.rating_action} by {rating.firm}")

                    event = MarketEvent(
                        event_type="rating",
                        ticker=rating.ticker,
                        source_id=rating.benzinga_id,
                        urgency=0.7,
                        data={"rating": rating.dict()}
                    )

                    signal = await self.run_event_driven(event)
                    if signal:
                        await self.process_signal(signal)

        except Exception as e:
            logger.error(f"Error checking ratings: {e}")

    async def check_earnings_events(self):
        """Check for earnings surprises."""
        try:
            # Fetch today's earnings
            earnings_response = await self.benzinga.get_earnings(
                ticker_any_of=self.watchlist,
                date=datetime.utcnow().strftime("%Y-%m-%d"),
                limit=20
            )

            for earnings in earnings_response.results:
                # Check for significant surprise
                if earnings.eps_surprise_percent and abs(earnings.eps_surprise_percent) > 10:
                    logger.info(f"EARNINGS SURPRISE for {earnings.ticker}: {earnings.eps_surprise_percent:.1f}%")

                    event = MarketEvent(
                        event_type="earnings",
                        ticker=earnings.ticker,
                        source_id=earnings.benzinga_id,
                        urgency=0.8,
                        data={"earnings": earnings.dict()}
                    )

                    signal = await self.run_event_driven(event)
                    if signal:
                        await self.process_signal(signal)

        except Exception as e:
            logger.error(f"Error checking earnings: {e}")

    async def run_event_driven(self, event: MarketEvent) -> Optional[StrategySignal]:
        """
        Process a market event and generate signal using AI agents.

        Args:
            event: Market event to process

        Returns:
            StrategySignal if action needed, None otherwise
        """
        logger.info(f"Processing {event.event_type} event for {event.ticker}")

        try:
            # Get current price
            quote = await self.alpaca.get_latest_quote(event.ticker)
            current_price = quote.last if quote else 0

            # Get account and positions for context
            account = await self.alpaca.get_account()
            positions = await self.alpaca.get_positions()
            account_dict = {"equity": float(account.equity), "buying_power": float(account.buying_power)} if account else None
            positions_list = [{"symbol": p.symbol, "qty": float(p.qty), "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else 0} for p in positions] if positions else []

            # Prepare news items from event data
            news_items = []
            if event.event_type == "news" and event.data.get("news"):
                news_data = event.data["news"]
                news_items = [news_data] if isinstance(news_data, dict) else news_data

            # Get latest news timestamp for cache check
            latest_news_ts = None
            if news_items:
                for item in news_items:
                    if isinstance(item.get("published"), datetime):
                        if latest_news_ts is None or item["published"] > latest_news_ts:
                            latest_news_ts = item["published"]

            # Run full AI analysis
            logger.info(f"Running AI agents for event-driven analysis of {event.ticker}")
            analysis = await run_full_analysis(
                ticker=event.ticker,
                news_items=news_items,
                current_price=current_price,
                bars=[],  # Event-driven doesn't need historical bars
                account=account_dict,
                positions=positions_list,
                latest_news_ts=latest_news_ts,
                force_llm=event.urgency > 0.9,  # Force LLM for urgent events
            )

            # Convert AI analysis to StrategySignal
            return self._analysis_to_signal(event.ticker, analysis, event.urgency)

        except Exception as e:
            logger.error(f"Error in AI-driven event analysis for {event.ticker}: {e}")
            return None

    async def run_interval_cycle(self) -> List[StrategySignal]:
        """
        Run systematic analysis on all watchlist tickers.

        Returns:
            List of signals to process
        """
        signals = []

        logger.info(f"Running interval cycle for {len(self.watchlist)} tickers")

        for ticker in self.watchlist:
            try:
                # Get comprehensive data
                data = await self.gather_ticker_data(ticker)

                # Analyze (would use full agent system)
                signal = await self.analyze_ticker(ticker, data)

                if signal and signal.final_score > self.settings.TRADING_MIN_SIGNAL_SCORE:
                    signals.append(signal)

            except Exception as e:
                logger.error(f"Error analyzing {ticker}: {e}")

        logger.info(f"Generated {len(signals)} signals in interval cycle")
        return signals

    async def gather_ticker_data(self, ticker: str) -> Dict[str, Any]:
        """Gather all relevant data for a ticker including price bars."""
        data = {}

        # Get news
        try:
            news = await self.benzinga.get_news(tickers=ticker, limit=10)
            data["news"] = news.results
            # Convert to dict format for AI agents
            data["news_items"] = [n.dict() if hasattr(n, 'dict') else n for n in news.results]
        except Exception as e:
            logger.debug(f"Error fetching news for {ticker}: {e}")
            data["news"] = []
            data["news_items"] = []

        # Get consensus
        try:
            consensus = await self.benzinga.get_consensus(ticker)
            data["consensus"] = consensus.results[0] if consensus.results else None
        except Exception as e:
            logger.debug(f"Error fetching consensus for {ticker}: {e}")
            data["consensus"] = None

        # Get recent ratings
        try:
            ratings = await self.benzinga.get_ratings(ticker=ticker, limit=5)
            data["ratings"] = ratings.results
        except Exception as e:
            logger.debug(f"Error fetching ratings for {ticker}: {e}")
            data["ratings"] = []

        # Get earnings data
        try:
            earnings = await self.benzinga.get_earnings(ticker=ticker, limit=1)
            data["earnings"] = earnings.results[0].dict() if earnings.results else None
        except Exception as e:
            logger.debug(f"Error fetching earnings for {ticker}: {e}")
            data["earnings"] = None

        # Get current price and bars from Alpaca
        try:
            quote = await self.alpaca.get_latest_quote(ticker)
            data["current_price"] = quote.last if quote else 0
            data["quote"] = quote
        except Exception as e:
            logger.debug(f"Error fetching quote for {ticker}: {e}")
            data["current_price"] = 0
            data["quote"] = None

        # Get historical bars for technical analysis
        try:
            bars = await self.alpaca.get_bars(ticker, timeframe="1D", limit=50)
            data["bars"] = [{"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars] if bars else []
        except Exception as e:
            logger.debug(f"Error fetching bars for {ticker}: {e}")
            data["bars"] = []

        # Get latest news timestamp for cache
        data["latest_news_ts"] = None
        if data["news"]:
            for item in data["news"]:
                published = item.published if hasattr(item, 'published') else item.get("published")
                if isinstance(published, datetime):
                    if data["latest_news_ts"] is None or published > data["latest_news_ts"]:
                        data["latest_news_ts"] = published

        return data

    async def analyze_ticker(self, ticker: str, data: Dict[str, Any]) -> Optional[StrategySignal]:
        """Analyze ticker data using AI agents and generate signal."""
        try:
            # Get account and positions for context
            account = await self.alpaca.get_account()
            positions = await self.alpaca.get_positions()
            account_dict = {"equity": float(account.equity), "buying_power": float(account.buying_power)} if account else None
            positions_list = [{"symbol": p.symbol, "qty": float(p.qty), "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else 0} for p in positions] if positions else []

            # Run full AI analysis with caching
            logger.info(f"Running AI agents for interval analysis of {ticker}")
            analysis = await run_full_analysis(
                ticker=ticker,
                news_items=data.get("news_items", []),
                current_price=data.get("current_price", 0),
                bars=data.get("bars", []),
                earnings=data.get("earnings"),
                account=account_dict,
                positions=positions_list,
                latest_news_ts=data.get("latest_news_ts"),
                force_llm=False,  # Use caching for interval analysis
            )

            # Convert AI analysis to StrategySignal
            return self._analysis_to_signal(ticker, analysis, urgency=0.5)

        except Exception as e:
            logger.error(f"Error in AI-driven analysis for {ticker}: {e}")
            return None

    def _analysis_to_signal(
        self, ticker: str, analysis: Dict[str, Any], urgency: float = 0.5
    ) -> Optional[StrategySignal]:
        """
        Convert AI agent analysis output to StrategySignal.

        Args:
            ticker: Stock ticker
            analysis: Output from run_full_analysis()
            urgency: Event urgency level (0-1)

        Returns:
            StrategySignal or None if analysis doesn't warrant a signal
        """
        try:
            synthesis = analysis.get("synthesis", {})
            news_agent = analysis.get("agents", {}).get("news", {})
            tech_agent = analysis.get("agents", {}).get("technical", {})

            # Get the final action and score
            final_action = synthesis.get("action", analysis.get("final_action", "HOLD"))
            final_score = synthesis.get("score", analysis.get("final_score", 50))
            confidence = synthesis.get("confidence", analysis.get("confidence", 50))

            # Map action to signal action
            action_map = {
                "STRONG_BUY": "STRONG_BUY",
                "BUY": "BUY",
                "HOLD": "HOLD",
                "SELL": "SELL",
                "STRONG_SELL": "STRONG_SELL",
                "AVOID": "HOLD",  # Map AVOID to HOLD
            }
            action = action_map.get(final_action, "HOLD")

            # Don't generate signals for HOLD actions unless very high score
            if action == "HOLD" and final_score < 70:
                logger.debug(f"Skipping signal for {ticker}: action={action}, score={final_score}")
                return None

            # Extract risk management from synthesis
            risk_mgmt = synthesis.get("risk_management", {})
            stop_loss_pct = risk_mgmt.get("stop_loss_percent", 3.0) / 100  # Convert to decimal
            take_profit_pct = (risk_mgmt.get("take_profit_1", 0) / analysis.get("current_price", 1) - 1) if analysis.get("current_price") else 0.08

            # Clamp values to valid ranges
            stop_loss_pct = max(0.01, min(0.5, stop_loss_pct if stop_loss_pct > 0 else 0.03))
            take_profit_pct = max(0.02, min(2.0, take_profit_pct if take_profit_pct > 0 else 0.08))

            # Determine time horizon
            time_horizon_map = {
                "scalp": "scalp",
                "day_trade": "scalp",
                "swing": "swing",
                "position": "position",
            }
            time_horizon = time_horizon_map.get(synthesis.get("time_horizon", "swing"), "swing")

            # Build AgentScore objects from analysis
            def build_agent_score(agent_data: Dict, default_urgency: float = 0.3) -> Dict:
                return {
                    "score": agent_data.get("score", 50),
                    "sentiment": self._sentiment_to_float(agent_data.get("sentiment", "neutral")),
                    "confidence": agent_data.get("confidence", 50) / 100 if agent_data.get("confidence", 50) > 1 else agent_data.get("confidence", 0.5),
                    "urgency": agent_data.get("urgency", default_urgency) if isinstance(agent_data.get("urgency"), (int, float)) else self._urgency_to_float(agent_data.get("urgency", "low")),
                    "notes": agent_data.get("summary", agent_data.get("thesis", "AI analysis"))[:200],
                }

            news_score = build_agent_score(news_agent, urgency)
            tech_score = build_agent_score(tech_agent, 0.3)

            # Build consensus score from synthesis
            consensus_score = {
                "score": synthesis.get("score", final_score),
                "sentiment": self._sentiment_to_float(synthesis.get("action", "HOLD")),
                "confidence": confidence / 100 if confidence > 1 else confidence,
                "urgency": urgency,
                "notes": synthesis.get("thesis", "Consensus analysis")[:200],
            }

            # Create default guidance and risk scores
            guidance_score = {
                "score": 50,
                "sentiment": 0.0,
                "confidence": 0.5,
                "urgency": 0.1,
                "notes": "No specific guidance data",
            }

            risk_score = {
                "score": 100 - final_score,  # Inverse of signal strength
                "sentiment": 0.0,
                "confidence": 0.6,
                "urgency": 0.1,
                "notes": "; ".join(synthesis.get("key_risks", ["Market risk"]))[:200],
            }

            signal = StrategySignal(
                ticker=ticker,
                action=action,
                final_score=final_score,
                news=news_score,
                earnings=guidance_score,  # Use guidance as earnings placeholder
                consensus=consensus_score,
                guidance=guidance_score,
                risk=risk_score,
                impact_score=final_score * (confidence / 100 if confidence > 1 else confidence),
                time_horizon=time_horizon,
                fast_reaction_mode=urgency > 0.8,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                reasoning_tree={
                    "ai_analysis": analysis,
                    "cache_stats": analysis.get("cache_stats", {}),
                    "cached_agents": analysis.get("cached_agents", {}),
                },
            )

            logger.info(
                f"Generated signal for {ticker}: {action} (score={final_score:.1f}, "
                f"confidence={confidence:.1f}%, cached={analysis.get('cached_agents', {})})"
            )
            return signal

        except Exception as e:
            logger.error(f"Error converting analysis to signal for {ticker}: {e}")
            return None

    def _sentiment_to_float(self, sentiment: Any) -> float:
        """Convert sentiment string or value to float (-1 to 1)."""
        if isinstance(sentiment, (int, float)):
            return max(-1, min(1, sentiment))

        sentiment_map = {
            "bullish": 0.7,
            "strong_buy": 0.9,
            "buy": 0.6,
            "neutral": 0.0,
            "hold": 0.0,
            "avoid": -0.3,
            "bearish": -0.7,
            "sell": -0.6,
            "strong_sell": -0.9,
        }
        return sentiment_map.get(str(sentiment).lower(), 0.0)

    def _urgency_to_float(self, urgency: Any) -> float:
        """Convert urgency string to float (0 to 1)."""
        if isinstance(urgency, (int, float)):
            return max(0, min(1, urgency))

        urgency_map = {
            "immediate": 0.95,
            "high": 0.8,
            "short_term": 0.6,
            "medium_term": 0.4,
            "medium": 0.4,
            "low": 0.2,
        }
        return urgency_map.get(str(urgency).lower(), 0.3)

    async def process_signal(self, signal: StrategySignal):
        """Process a signal and potentially execute trade."""
        logger.info(f"Processing signal for {signal.ticker}: {signal.action} (score: {signal.final_score:.1f})")

        try:
            # Get account and positions
            account = await self.alpaca.get_account()
            positions = await self.alpaca.get_positions()

            # Get current price
            quote = await self.alpaca.get_latest_quote(signal.ticker)

            # Evaluate risk
            risk_decision = await self.risk_engine.evaluate_risk(
                signal=signal,
                account=account,
                positions=positions,
                current_price=quote.last
            )

            if not risk_decision.allowed:
                logger.warning(f"Trade blocked by risk engine: {risk_decision.reason}")
                return

            # Create order
            order = TradeOrder(
                ticker=signal.ticker,
                side="buy" if signal.action in ["BUY", "STRONG_BUY"] else "sell",
                quantity=risk_decision.suggested_shares,
                order_type="bracket" if signal.fast_reaction_mode else "limit",
                limit_price=quote.last * (1.001 if signal.action == "BUY" else 0.999),
                stop_price=quote.last * (1 - signal.stop_loss_pct),
                take_profit_price=quote.last * (1 + signal.take_profit_pct),
                time_in_force="day",
                env=self.settings.ALPACA_ENV
            )

            # Execute trade
            result = await self.alpaca.place_order(order)
            logger.info(f"✅ Order placed: {result.id} for {signal.ticker}")

        except Exception as e:
            logger.error(f"Failed to process signal for {signal.ticker}: {e}")


async def main():
    """Main entry point for the orchestrator."""
    orchestrator = HybridOrchestrator()
    await orchestrator.start()


if __name__ == "__main__":
    asyncio.run(main())