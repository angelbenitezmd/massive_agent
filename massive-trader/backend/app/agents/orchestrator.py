"""Hybrid orchestrator for event-driven and interval-based trading."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from app.core.config import get_settings
from app.models.signals import StrategySignal, MarketEvent
from app.models.trading import TradeOrder
from app.services.benzinga_client import BenzingaClient
from app.services.alpaca_client import AlpacaClient
from app.services.risk_engine import RiskEngine

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
                    published_gte=datetime.utcnow() - timedelta(hours=1),
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
        Process a market event and generate signal if appropriate.

        Args:
            event: Market event to process

        Returns:
            StrategySignal if action needed, None otherwise
        """
        logger.info(f"Processing {event.event_type} event for {event.ticker}")

        # This would call the full agent system
        # For now, return a mock signal for demonstration
        if event.urgency > 0.8:
            # High urgency - generate signal
            signal = StrategySignal(
                ticker=event.ticker,
                action="BUY" if event.event_type != "negative_news" else "SELL",
                final_score=75.0,
                news={"score": 70, "sentiment": 0.5, "confidence": 0.7, "urgency": event.urgency, "notes": "Event-driven"},
                earnings={"score": 60, "sentiment": 0.3, "confidence": 0.6, "urgency": 0.5, "notes": "Neutral"},
                consensus={"score": 65, "sentiment": 0.4, "confidence": 0.7, "urgency": 0.3, "notes": "Positive"},
                guidance={"score": 55, "sentiment": 0.1, "confidence": 0.5, "urgency": 0.2, "notes": "Neutral"},
                risk={"score": 30, "sentiment": 0, "confidence": 0.8, "urgency": 0.1, "notes": "Low risk"},
                impact_score=70.0,
                time_horizon="scalp" if event.urgency > 0.9 else "swing",
                fast_reaction_mode=event.urgency > 0.8,
                stop_loss_pct=0.02,
                take_profit_pct=0.05
            )

            return signal

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
        """Gather all relevant data for a ticker."""
        data = {}

        # Get news
        try:
            news = await self.benzinga.get_news(tickers=ticker, limit=10)
            data["news"] = news.results
        except:
            data["news"] = []

        # Get consensus
        try:
            consensus = await self.benzinga.get_consensus(ticker)
            data["consensus"] = consensus.results[0] if consensus.results else None
        except:
            data["consensus"] = None

        # Get recent ratings
        try:
            ratings = await self.benzinga.get_ratings(ticker=ticker, limit=5)
            data["ratings"] = ratings.results
        except:
            data["ratings"] = []

        return data

    async def analyze_ticker(self, ticker: str, data: Dict[str, Any]) -> Optional[StrategySignal]:
        """Analyze ticker data and generate signal."""
        # Simplified analysis (real system would use agents)
        has_news = len(data.get("news", [])) > 0
        has_positive_consensus = data.get("consensus") and data["consensus"].consensus_rating in ["buy", "strong_buy"]

        if has_news and has_positive_consensus:
            return StrategySignal(
                ticker=ticker,
                action="BUY",
                final_score=65.0,
                news={"score": 60, "sentiment": 0.3, "confidence": 0.6, "urgency": 0.3, "notes": "Interval"},
                earnings={"score": 50, "sentiment": 0, "confidence": 0.5, "urgency": 0.1, "notes": "Neutral"},
                consensus={"score": 70, "sentiment": 0.5, "confidence": 0.7, "urgency": 0.2, "notes": "Positive"},
                guidance={"score": 50, "sentiment": 0, "confidence": 0.5, "urgency": 0.1, "notes": "Neutral"},
                risk={"score": 40, "sentiment": 0, "confidence": 0.6, "urgency": 0.1, "notes": "Moderate"},
                impact_score=62.0,
                time_horizon="swing",
                fast_reaction_mode=False,
                stop_loss_pct=0.03,
                take_profit_pct=0.08
            )

        return None

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