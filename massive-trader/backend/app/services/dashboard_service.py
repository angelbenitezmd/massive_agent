"""Aggregate market, AI agent, and risk data for the Streamlit dashboard."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.errors import (
    AlpacaAPIError,
    BenzingaAPIError,
    RiskEngineError,
)
from app.models.earnings import EarningsItem
from app.models.news import NewsItem
from app.models.signals import AgentScore, StrategySignal
from app.models.trading import AccountModel, PositionModel, QuoteModel
from app.services.alpaca_client import AlpacaClient
from app.services.benzinga_client import BenzingaClient
from app.services.risk_engine import RiskDecision, RiskEngine

logger = logging.getLogger(__name__)


def _quick_news_sentiment(news_items: List[NewsItem]) -> Dict[str, float]:
    """
    Quick sentiment analysis based on keywords.
    Standalone version to avoid langchain dependency.
    """
    positive_keywords = {
        "upgrade", "beat", "surpass", "exceed", "positive", "growth",
        "profit", "revenue", "bullish", "buy", "outperform", "strong"
    }

    negative_keywords = {
        "downgrade", "miss", "below", "negative", "loss", "decline",
        "bearish", "sell", "underperform", "weak", "concern", "risk"
    }

    positive_count = 0
    negative_count = 0
    total_count = len(news_items)

    for item in news_items:
        text = (item.title + " " + (item.teaser or "")).lower()

        for keyword in positive_keywords:
            if keyword in text:
                positive_count += 1
                break

        for keyword in negative_keywords:
            if keyword in text:
                negative_count += 1
                break

    if total_count == 0:
        return {"sentiment": 0.0, "confidence": 0.0}

    sentiment = (positive_count - negative_count) / total_count
    confidence = (positive_count + negative_count) / total_count

    return {"sentiment": sentiment, "confidence": confidence}


def _safe_iso(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO string safely."""
    return dt.isoformat() if isinstance(dt, datetime) else None


def _sma(prices: List[float], window: int) -> Optional[float]:
    """Simple moving average."""
    if len(prices) < window or window <= 0:
        return None
    return sum(prices[-window:]) / window


def _ema(prices: List[float], window: int) -> Optional[float]:
    """Exponential moving average."""
    if len(prices) < window or window <= 0:
        return None
    k = 2 / (window + 1)
    ema_val = prices[0]
    for price in prices[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def _rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index calculation."""
    if len(prices) <= period:
        return None

    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains.append(delta)
        else:
            losses.append(abs(delta))

    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 0

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(prices: List[float]) -> Dict[str, Optional[float]]:
    """MACD using standard 12/26 EMA and 9 EMA signal."""
    if len(prices) < 35:
        return {"macd": None, "signal": None, "histogram": None}

    def ema_series(values: List[float], window: int) -> List[float]:
        series: List[float] = []
        k = 2 / (window + 1)
        ema_val = values[0]
        series.append(ema_val)
        for price in values[1:]:
            ema_val = price * k + ema_val * (1 - k)
            series.append(ema_val)
        return series

    ema_short = ema_series(prices, 12)
    ema_long = ema_series(prices, 26)
    macd_series = [s - l for s, l in zip(ema_short[-len(ema_long):], ema_long)]
    signal_series = ema_series(macd_series, 9)

    macd_val = macd_series[-1] if macd_series else None
    signal_val = signal_series[-1] if signal_series else None
    hist_val = macd_val - signal_val if macd_val is not None and signal_val is not None else None

    return {"macd": macd_val, "signal": signal_val, "histogram": hist_val}


def _clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a float into [lower, upper]."""
    return max(lower, min(upper, value))


class DashboardService:
    """Fetch and aggregate data for the dashboard."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.risk_engine = RiskEngine()

    async def _fetch_quote_and_bars(
        self, ticker: str, alpaca: AlpacaClient
    ) -> Tuple[Optional[QuoteModel], List[Dict[str, Any]]]:
        """Fetch quote and bars in parallel for better performance."""
        quote: Optional[QuoteModel] = None
        bars: List[Dict[str, Any]] = []

        # Fetch quote and bars in parallel
        async def fetch_quote():
            try:
                return await alpaca.get_latest_quote(ticker)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to fetch quote for {ticker}: {exc}")
                return None

        async def fetch_bars():
            try:
                # Reduced to 100 bars for faster response (still enough for technical analysis)
                return await alpaca.get_bars(ticker, timeframe="5Min", limit=100)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to fetch bars for {ticker}: {exc}")
                return []

        quote, bars = await asyncio.gather(fetch_quote(), fetch_bars())
        return quote, bars

    async def _fetch_news_and_earnings(
        self, ticker: str, benzinga: BenzingaClient
    ) -> Tuple[List[NewsItem], List[EarningsItem]]:
        """Fetch news and earnings in parallel for better performance."""
        news_items: List[NewsItem] = []
        earnings_items: List[EarningsItem] = []

        # Fetch news and earnings in parallel
        async def fetch_news():
            try:
                # Reduced to 1 day for faster response
                news_resp = await benzinga.get_news(
                    tickers=ticker,
                    published_gte=(datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
                    limit=15,
                )
                return news_resp.results
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to fetch news for {ticker}: {exc}")
                return []

        async def fetch_earnings():
            try:
                earnings_resp = await benzinga.get_earnings(
                    ticker=ticker,
                    date_gte=(datetime.utcnow() - timedelta(days=120)).date(),
                    limit=3,
                    sort="date.desc",
                )
                return earnings_resp.results
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to fetch earnings for {ticker}: {exc}")
                return []

        news_items, earnings_items = await asyncio.gather(fetch_news(), fetch_earnings())
        return news_items, earnings_items

    def _analyze_news(self, news_items: List[NewsItem]) -> AgentScore:
        """Create a lightweight news sentiment signal without LLM."""
        sentiment_metrics = _quick_news_sentiment(news_items)
        sentiment = sentiment_metrics.get("sentiment", 0.0)
        confidence = sentiment_metrics.get("confidence", 0.0)
        score = _clamp(50 + sentiment * 50, 0, 100)

        urgency = 0.0
        if news_items:
            latest = news_items[0]
            age_seconds = (datetime.now(timezone.utc) - latest.published).total_seconds()
            if age_seconds < 300:
                urgency = 0.9
            elif age_seconds < 3600:
                urgency = 0.6
            elif age_seconds < 6 * 3600:
                urgency = 0.4
            else:
                urgency = 0.2

        notes = "No recent news" if not news_items else f"Analyzed {len(news_items)} items"
        return AgentScore(
            score=score,
            sentiment=_clamp(sentiment, -1, 1),
            confidence=_clamp(confidence, 0, 1),
            urgency=_clamp(urgency, 0, 1),
            notes=notes,
        )

    def _analyze_earnings(self, earnings_items: List[EarningsItem]) -> AgentScore:
        """Score earnings based on surprise percentages."""
        if not earnings_items:
            return AgentScore(
                score=50.0,
                sentiment=0.0,
                confidence=0.1,
                urgency=0.1,
                notes="No recent earnings",
            )

        latest = earnings_items[0]
        eps_surprise = latest.eps_surprise_percent or 0.0
        rev_surprise = latest.revenue_surprise_percent or 0.0
        combined = (eps_surprise + rev_surprise) / 2
        score = _clamp(50 + combined, 0, 100)
        sentiment = 1.0 if combined > 0 else -1.0 if combined < 0 else 0.0
        confidence = _clamp(abs(combined) / 20 + 0.4, 0, 1)
        urgency = 0.5 if latest.date >= datetime.utcnow().date() - timedelta(days=7) else 0.2
        notes = f"EPS surprise {eps_surprise:.1f}%, Revenue surprise {rev_surprise:.1f}%"

        return AgentScore(
            score=score,
            sentiment=sentiment,
            confidence=confidence,
            urgency=urgency,
            notes=notes,
        )

    def _analyze_technicals(
        self,
        bars: List[Dict[str, Any]],
        latest_price: Optional[float],
    ) -> Dict[str, Any]:
        """Calculate technical indicators and return an AgentScore plus raw values."""
        if not bars:
            bars = []
        closes = [bar.get("c") or bar.get("close") for bar in bars if bar.get("c") or bar.get("close")]
        if not closes and latest_price:
            closes = [latest_price]

        rsi_val = _rsi(closes) if closes else None
        macd_vals = _macd(closes) if closes else {"macd": None, "signal": None, "histogram": None}
        sma_20 = _sma(closes, 20)
        sma_50 = _sma(closes, 50)
        sma_200 = _sma(closes, 200) if len(closes) >= 200 else None
        ema_20 = _ema(closes, 20)
        ema_50 = _ema(closes, 50)

        bullish = 0
        bearish = 0

        if rsi_val is not None:
            if rsi_val < 35:
                bullish += 1
            elif rsi_val > 65:
                bearish += 1

        if macd_vals["histogram"] is not None:
            if macd_vals["histogram"] > 0:
                bullish += 1
            elif macd_vals["histogram"] < 0:
                bearish += 1

        if latest_price and sma_20 and sma_50:
            if latest_price > sma_20 > sma_50:
                bullish += 1
            elif latest_price < sma_20 < sma_50:
                bearish += 1

        score = _clamp(50 + (bullish - bearish) * 10, 0, 100)
        sentiment = 0.0
        if bullish > bearish:
            sentiment = 0.5
        elif bearish > bullish:
            sentiment = -0.5

        tech_score = AgentScore(
            score=score,
            sentiment=sentiment,
            confidence=0.6 if bullish != bearish else 0.3,
            urgency=0.3,
            notes="RSI/MACD/MAs blend",
        )

        return {
            "score": tech_score,
            "indicators": {
                "rsi": rsi_val,
                "macd": macd_vals.get("macd"),
                "macd_signal": macd_vals.get("signal"),
                "macd_histogram": macd_vals.get("histogram"),
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
                "ema_20": ema_20,
                "ema_50": ema_50,
            },
        }

    def _consensus_action(
        self,
        news: AgentScore,
        earnings: AgentScore,
        technicals: AgentScore,
    ) -> Tuple[str, float]:
        """Combine agent scores into a final action and composite score."""
        scores = [news.score, earnings.score, technicals.score]
        final_score = sum(scores) / len(scores)

        bullish_votes = sum(1 for s in [news, earnings, technicals] if s.score >= 60 and s.sentiment >= 0)
        bearish_votes = sum(1 for s in [news, earnings, technicals] if s.score <= 40 and s.sentiment <= 0)

        if bullish_votes >= 2 and final_score >= self.settings.TRADING_MIN_SIGNAL_SCORE:
            return "BUY", final_score
        if bearish_votes >= 2:
            return "SELL", final_score
        if final_score < self.settings.TRADING_MIN_SIGNAL_SCORE:
            return "HOLD", final_score
        return "HOLD", final_score

    async def _evaluate_risk(
        self,
        signal: StrategySignal,
        account: AccountModel,
        positions: List[PositionModel],
        price: float,
    ) -> Tuple[Optional[RiskDecision], Optional[str]]:
        """Run risk engine and capture exceptions as messages."""
        try:
            decision = await self.risk_engine.evaluate_risk(
                signal=signal,
                account=account,
                positions=positions,
                current_price=price,
            )
            return decision, None
        except RiskEngineError as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Unexpected risk evaluation error: {exc}")
            return None, str(exc)

    def _circuit_breaker_level(
        self, account: Optional[AccountModel]
    ) -> Tuple[str, Optional[float]]:
        """Determine circuit breaker level based on daily P&L."""
        if not account or account.portfolio_value == 0:
            return "UNKNOWN", None

        daily_pnl = account.equity - account.last_equity
        pnl_pct = daily_pnl / account.last_equity if account.last_equity and account.last_equity > 0 else 0.0

        max_loss = self.settings.TRADING_DAILY_MAX_DRAWDOWN
        if pnl_pct <= -max_loss:
            return "RED", pnl_pct
        if pnl_pct <= -0.75 * max_loss:
            return "ORANGE", pnl_pct
        if pnl_pct <= -0.5 * max_loss:
            return "YELLOW", pnl_pct
        return "GREEN", pnl_pct

    async def get_dashboard_state(self, ticker: str) -> Dict[str, Any]:
        """Aggregate all data needed for the Streamlit dashboard."""
        ticker = ticker.upper()
        errors: List[str] = []

        async with AlpacaClient() as alpaca, BenzingaClient() as benzinga:
            # Fetch all independent data in parallel for maximum performance
            async def fetch_market_data():
                return await self._fetch_quote_and_bars(ticker, alpaca)

            async def fetch_benzinga_data():
                return await self._fetch_news_and_earnings(ticker, benzinga)

            async def fetch_account_data():
                account: Optional[AccountModel] = None
                positions: List[PositionModel] = []
                try:
                    # Fetch account and positions in parallel
                    account_task = alpaca.get_account()
                    positions_task = alpaca.get_positions()
                    account, positions = await asyncio.gather(
                        account_task, positions_task, return_exceptions=True
                    )
                    # Handle exceptions
                    if isinstance(account, Exception):
                        logger.error(f"Failed to fetch account: {account}")
                        account = None
                        errors.append("Unable to fetch account")
                    if isinstance(positions, Exception):
                        logger.error(f"Failed to fetch positions: {positions}")
                        positions = []
                        errors.append("Unable to fetch positions")
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"Failed to fetch account/positions: {exc}")
                    errors.append("Unable to fetch account or positions")
                return account, positions

            # Run all three groups in parallel
            (quote, bars), (news_items, earnings_items), (account, positions) = await asyncio.gather(
                fetch_market_data(),
                fetch_benzinga_data(),
                fetch_account_data(),
            )

        news_score = self._analyze_news(news_items)
        earnings_score = self._analyze_earnings(earnings_items)
        tech_results = self._analyze_technicals(bars, quote.last if quote else None)
        technical_score: AgentScore = tech_results["score"]

        action, final_score = self._consensus_action(news_score, earnings_score, technical_score)

        stop_loss_pct = 0.02 if action == "BUY" else 0.03
        take_profit_pct = 0.04 if action == "BUY" else 0.03

        strategy_signal = StrategySignal(
            ticker=ticker,
            action=action,
            final_score=final_score,
            news=news_score,
            earnings=earnings_score,
            consensus=AgentScore(
                score=final_score,
                sentiment=(news_score.sentiment + earnings_score.sentiment + technical_score.sentiment) / 3,
                confidence=min(1.0, (news_score.confidence + earnings_score.confidence + technical_score.confidence) / 3),
                urgency=max(news_score.urgency, earnings_score.urgency, technical_score.urgency),
                notes="Weighted blend",
            ),
            guidance=AgentScore(score=50, sentiment=0, confidence=0.3, urgency=0.1, notes="Not implemented"),
            risk=AgentScore(score=50, sentiment=0, confidence=0.5, urgency=0.1, notes="Pre-trade risk"),
            impact_score=final_score,
            time_horizon="scalp" if news_score.urgency > 0.6 else "swing",
            fast_reaction_mode=news_score.urgency > self.settings.TRADING_FAST_MODE_URGENCY_THRESHOLD,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        risk_decision: Optional[RiskDecision] = None
        risk_message: Optional[str] = None
        if account and quote and quote.last and quote.last > 0:
            risk_decision, risk_message = await self._evaluate_risk(
                strategy_signal,
                account,
                positions,
                quote.last,
            )
        elif not account:
            risk_message = "Account unavailable - cannot size trade"
        elif not quote or not quote.last or quote.last <= 0:
            risk_message = "Quote unavailable - cannot size trade"

        circuit_level, daily_pnl_pct = self._circuit_breaker_level(account)

        # Format news and earnings for UI
        news_payload = [
            {
                "title": item.title,
                "published": _safe_iso(item.published),
                "channels": item.channels[:5],
                "tags": item.tags[:8],
                "url": item.url,
                "teaser": item.teaser,
                "ticker_mentions": item.tickers,
            }
            for item in news_items[:8]
        ]

        earnings_payload = [
            {
                "ticker": item.ticker,
                "date": item.date.isoformat(),
                "time": item.time,
                "eps_actual": item.actual_eps,
                "eps_estimate": item.estimated_eps,
                "eps_surprise_pct": item.eps_surprise_percent,
                "revenue_actual": item.actual_revenue,
                "revenue_estimate": item.estimated_revenue,
                "revenue_surprise_pct": item.revenue_surprise_percent,
                "importance": item.importance,
            }
            for item in earnings_items[:3]
        ]

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "ticker": ticker,
            "environment": {
                "alpaca_env": self.settings.ALPACA_ENV,
                "paper_trading": self.settings.is_paper_trading,
                "watchlist": self.settings.watchlist,
            },
            "market": {
                "quote": quote.dict() if quote else None,
                "bars": bars,
                "technicals": tech_results["indicators"],
            },
            "news": {
                "items": news_payload,
                "agent": news_score.dict(),
            },
            "earnings": {
                "items": earnings_payload,
                "agent": earnings_score.dict(),
            },
            "technical_agent": technical_score.dict(),
            "consensus": {
                "action": action,
                "final_score": final_score,
                "time_horizon": strategy_signal.time_horizon,
                "fast_reaction_mode": strategy_signal.fast_reaction_mode,
                "stop_loss_pct": strategy_signal.stop_loss_pct,
                "take_profit_pct": strategy_signal.take_profit_pct,
                "contributing_agents": {
                    "news": news_score.dict(),
                    "earnings": earnings_score.dict(),
                    "technical": technical_score.dict(),
                },
            },
            "risk": {
                "decision": risk_decision.dict() if risk_decision else None,
                "message": risk_message,
                "circuit_breaker": circuit_level,
                "daily_pnl_pct": daily_pnl_pct,
            },
            "account": account.dict() if account else None,
            "positions": [pos.dict() for pos in positions] if positions else [],
            "errors": errors,
        }
