"""
Trade Timing Agent - Entry Timing Optimization.

This agent specializes in determining the optimal time and price
to enter a trade for maximum efficiency.

Key responsibilities:
- VWAP analysis
- Intraday momentum patterns
- Volume profile analysis
- Time-of-day effects
- Liquidity assessment
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from app.services.llm_service import llm_service, LLMProvider
from app.services.agent_cache import agent_cache, AgentType

logger = logging.getLogger(__name__)


class TimingAction(Enum):
    """Recommended timing action."""
    IMMEDIATE = "immediate"  # Enter now
    WAIT_PULLBACK = "wait_pullback"  # Wait for price to pull back
    WAIT_BREAKOUT = "wait_breakout"  # Wait for breakout confirmation
    WAIT_OPEN = "wait_open"  # Wait for market open
    WAIT_CLOSE = "wait_close"  # Wait for power hour
    DEFER = "defer"  # Defer to another day
    LIMIT_ORDER = "limit_order"  # Use limit order at specific price


class TimeOfDay(Enum):
    """Time of day categories."""
    PRE_MARKET = "pre_market"  # 4:00 - 9:30 ET
    OPEN_VOLATILITY = "open_volatility"  # 9:30 - 10:00 ET
    MORNING = "morning"  # 10:00 - 12:00 ET
    MIDDAY = "midday"  # 12:00 - 14:00 ET
    AFTERNOON = "afternoon"  # 14:00 - 15:30 ET
    POWER_HOUR = "power_hour"  # 15:30 - 16:00 ET
    AFTER_HOURS = "after_hours"  # 16:00 - 20:00 ET


@dataclass
class TimingRecommendation:
    """Output from TradeTimingAgent analysis."""
    action: TimingAction
    optimal_entry_price: float
    entry_zone_low: float
    entry_zone_high: float

    time_recommendation: str  # Specific time recommendation
    current_time_of_day: TimeOfDay
    preferred_time_of_day: Optional[TimeOfDay]

    vwap: float
    price_vs_vwap: float  # % above/below VWAP
    vwap_recommendation: str  # Buy below VWAP, etc.

    liquidity_score: float  # 0-100
    spread_assessment: str  # "tight", "normal", "wide"
    volume_assessment: str  # "high", "normal", "low"

    momentum_direction: str  # "bullish", "bearish", "neutral"
    momentum_strength: float  # 0-100

    urgency: float  # 0-100 (how urgent is the entry)
    patience_reward: float  # Expected improvement from waiting

    entry_signals: List[str] = field(default_factory=list)
    wait_signals: List[str] = field(default_factory=list)

    score: float = 50  # 0-100 (0=bad timing, 100=perfect timing)
    confidence: float = 50

    reasoning: str = ""
    agent: str = "TradeTimingAgent"
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "optimal_entry_price": self.optimal_entry_price,
            "entry_zone_low": self.entry_zone_low,
            "entry_zone_high": self.entry_zone_high,
            "time_recommendation": self.time_recommendation,
            "current_time_of_day": self.current_time_of_day.value,
            "preferred_time_of_day": self.preferred_time_of_day.value if self.preferred_time_of_day else None,
            "vwap": self.vwap,
            "price_vs_vwap": self.price_vs_vwap,
            "vwap_recommendation": self.vwap_recommendation,
            "liquidity_score": self.liquidity_score,
            "spread_assessment": self.spread_assessment,
            "volume_assessment": self.volume_assessment,
            "momentum_direction": self.momentum_direction,
            "momentum_strength": self.momentum_strength,
            "urgency": self.urgency,
            "patience_reward": self.patience_reward,
            "entry_signals": self.entry_signals,
            "wait_signals": self.wait_signals,
            "score": self.score,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "agent": self.agent,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class TradeTimingAgent:
    """
    Trade timing optimization agent.

    Uses Claude to determine:
    1. Optimal entry price
    2. Best time of day to enter
    3. VWAP-based entry strategies
    4. Liquidity assessment
    5. Intraday momentum analysis
    """

    SYSTEM_PROMPT = """You are a trade execution specialist focused on optimal entry timing.
Your job is to get the best possible entry price for trades.

You must assess:
1. **Price vs VWAP**: Is the stock above or below VWAP?
2. **Time of Day**: What time-of-day effects are at play?
3. **Intraday Momentum**: Is momentum in your favor?
4. **Liquidity**: Is there enough volume? What's the spread?
5. **Patience Reward**: How much could waiting improve the entry?

Entry timing principles:
- Avoid the first 30 minutes (high volatility, wide spreads)
- Power hour (3:30-4:00 PM ET) often has strong moves
- Buy below VWAP when possible
- Wait for pullbacks in uptrends
- Wait for breakout confirmation in ranges
- Consider spread cost in illiquid names
- Don't chase extended moves

Return your analysis in JSON format."""

    @staticmethod
    async def analyze(
        ticker: str,
        current_price: float,
        action: str,  # BUY or SELL
        vwap: float,
        intraday_bars: List[Dict],
        current_spread: float,
        current_volume: int,
        avg_volume: int,
        time_of_day: str,
        session_high: Optional[float] = None,
        session_low: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> TimingRecommendation:
        """
        Analyze optimal entry timing.

        Args:
            ticker: Stock ticker
            current_price: Current stock price
            action: BUY or SELL
            vwap: Volume Weighted Average Price
            intraday_bars: Intraday price bars
            current_spread: Current bid-ask spread
            current_volume: Current session volume
            avg_volume: Average daily volume
            time_of_day: Current time category
            session_high: Session high price
            session_low: Session low price
            atr: Average True Range

        Returns:
            TimingRecommendation with optimal entry strategy
        """
        # Calculate metrics
        price_vs_vwap = ((current_price - vwap) / vwap) * 100 if vwap > 0 else 0
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        spread_pct = (current_spread / current_price) * 100 if current_price > 0 else 0

        # Format intraday bars
        bars_text = ""
        if intraday_bars:
            recent_bars = intraday_bars[-10:]
            for bar in recent_bars:
                time_str = bar.get("time", bar.get("timestamp", ""))
                close = bar.get("close", 0)
                volume = bar.get("volume", 0)
                bars_text += f"  {time_str}: ${close:.2f} (vol: {volume:,})\n"

        user_prompt = f"""Analyze entry timing for this trade:

TRADE:
- Ticker: {ticker}
- Action: {action}
- Current Price: ${current_price:.2f}

INTRADAY DATA:
- VWAP: ${vwap:.2f}
- Price vs VWAP: {price_vs_vwap:+.2f}%
- Session High: ${session_high:.2f if session_high else "N/A"}
- Session Low: ${session_low:.2f if session_low else "N/A"}
- ATR (volatility): ${atr:.2f if atr else "N/A"}

LIQUIDITY:
- Current Spread: ${current_spread:.4f} ({spread_pct:.3f}%)
- Current Volume: {current_volume:,}
- Average Volume: {avg_volume:,}
- Volume Ratio: {volume_ratio:.2f}x average

TIMING:
- Time of Day: {time_of_day}

RECENT PRICE ACTION:
{bars_text or "No intraday data available"}

Provide your timing recommendation in this JSON format:
{{
    "action": "immediate" | "wait_pullback" | "wait_breakout" | "wait_open" | "wait_close" | "defer" | "limit_order",
    "optimal_entry_price": <best entry price>,
    "entry_zone_low": <lower bound of entry zone>,
    "entry_zone_high": <upper bound of entry zone>,
    "time_recommendation": "<specific timing advice>",
    "preferred_time_of_day": "pre_market" | "open_volatility" | "morning" | "midday" | "afternoon" | "power_hour" | null,
    "vwap_recommendation": "<VWAP-based advice>",
    "liquidity_score": <0-100>,
    "spread_assessment": "tight" | "normal" | "wide",
    "volume_assessment": "high" | "normal" | "low",
    "momentum_direction": "bullish" | "bearish" | "neutral",
    "momentum_strength": <0-100>,
    "urgency": <0-100, how urgent is entry>,
    "patience_reward": <expected % improvement from waiting>,
    "entry_signals": ["<signals suggesting enter now>"],
    "wait_signals": ["<signals suggesting wait>"],
    "score": <0-100, timing quality>,
    "confidence": <0-100>,
    "reasoning": "<2-3 sentence timing recommendation>"
}}"""

        result = await llm_service.analyze(
            system_prompt=TradeTimingAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.OPENAI,  # OpenAI for faster response
            temperature=0.2
        )

        if result.get("error"):
            logger.warning(f"TradeTimingAgent error: {result['error']}")
            return TradeTimingAgent._fallback_analysis(
                ticker, current_price, action, vwap, time_of_day, spread_pct
            )

        # Determine current time of day enum
        try:
            current_tod = TimeOfDay(time_of_day.lower().replace(" ", "_"))
        except ValueError:
            current_tod = TimeOfDay.MORNING

        # Parse result into TimingRecommendation
        try:
            preferred_tod = None
            if result.get("preferred_time_of_day"):
                try:
                    preferred_tod = TimeOfDay(result["preferred_time_of_day"])
                except ValueError:
                    pass

            return TimingRecommendation(
                action=TimingAction(result.get("action", "immediate")),
                optimal_entry_price=float(result.get("optimal_entry_price", current_price)),
                entry_zone_low=float(result.get("entry_zone_low", current_price * 0.99)),
                entry_zone_high=float(result.get("entry_zone_high", current_price * 1.01)),
                time_recommendation=result.get("time_recommendation", ""),
                current_time_of_day=current_tod,
                preferred_time_of_day=preferred_tod,
                vwap=vwap,
                price_vs_vwap=price_vs_vwap,
                vwap_recommendation=result.get("vwap_recommendation", ""),
                liquidity_score=float(result.get("liquidity_score", 70)),
                spread_assessment=result.get("spread_assessment", "normal"),
                volume_assessment=result.get("volume_assessment", "normal"),
                momentum_direction=result.get("momentum_direction", "neutral"),
                momentum_strength=float(result.get("momentum_strength", 50)),
                urgency=float(result.get("urgency", 50)),
                patience_reward=float(result.get("patience_reward", 0)),
                entry_signals=result.get("entry_signals", []),
                wait_signals=result.get("wait_signals", []),
                score=float(result.get("score", 50)),
                confidence=float(result.get("confidence", 50)),
                reasoning=result.get("reasoning", ""),
                provider=result.get("provider", "openai"),
            )
        except Exception as e:
            logger.error(f"Error parsing TradeTimingAgent result: {e}")
            return TradeTimingAgent._fallback_analysis(
                ticker, current_price, action, vwap, time_of_day, spread_pct
            )

    @staticmethod
    async def analyze_with_cache(
        ticker: str,
        current_price: float,
        action: str,
        vwap: float,
        intraday_bars: List[Dict],
        current_spread: float,
        current_volume: int,
        avg_volume: int,
        time_of_day: str,
        session_high: Optional[float] = None,
        session_low: Optional[float] = None,
        atr: Optional[float] = None,
        force: bool = False,
    ) -> TimingRecommendation:
        """
        Timing analysis with caching.

        Timing is highly dynamic, so cache is very short-lived.
        """
        ticker = ticker.upper()

        # Very dynamic, short cache
        cache_hash = agent_cache._hash_data({
            "ticker": ticker,
            "price_bucket": round(current_price, 1),
            "time": time_of_day,
        })

        if not force:
            cached = agent_cache.get_cached_signal(ticker, AgentType.TIMING)
            if cached and cached.get("_cache_hash") == cache_hash:
                logger.info(f"TradeTimingAgent for {ticker}: Using cached result")
                try:
                    current_tod = TimeOfDay(cached.get("current_time_of_day", "morning"))
                    preferred_tod = None
                    if cached.get("preferred_time_of_day"):
                        try:
                            preferred_tod = TimeOfDay(cached["preferred_time_of_day"])
                        except ValueError:
                            pass

                    return TimingRecommendation(
                        action=TimingAction(cached.get("action", "immediate")),
                        optimal_entry_price=cached.get("optimal_entry_price", current_price),
                        entry_zone_low=cached.get("entry_zone_low", current_price * 0.99),
                        entry_zone_high=cached.get("entry_zone_high", current_price * 1.01),
                        time_recommendation=cached.get("time_recommendation", ""),
                        current_time_of_day=current_tod,
                        preferred_time_of_day=preferred_tod,
                        vwap=cached.get("vwap", vwap),
                        price_vs_vwap=cached.get("price_vs_vwap", 0),
                        vwap_recommendation=cached.get("vwap_recommendation", ""),
                        liquidity_score=cached.get("liquidity_score", 70),
                        spread_assessment=cached.get("spread_assessment", "normal"),
                        volume_assessment=cached.get("volume_assessment", "normal"),
                        momentum_direction=cached.get("momentum_direction", "neutral"),
                        momentum_strength=cached.get("momentum_strength", 50),
                        urgency=cached.get("urgency", 50),
                        patience_reward=cached.get("patience_reward", 0),
                        entry_signals=cached.get("entry_signals", []),
                        wait_signals=cached.get("wait_signals", []),
                        score=cached.get("score", 50),
                        confidence=cached.get("confidence", 50),
                        reasoning=cached.get("reasoning", ""),
                        provider="cache",
                    )
                except Exception:
                    pass

        # Run analysis
        logger.info(f"TradeTimingAgent for {ticker}: Running LLM analysis")
        signal = await TradeTimingAgent.analyze(
            ticker=ticker,
            current_price=current_price,
            action=action,
            vwap=vwap,
            intraday_bars=intraday_bars,
            current_spread=current_spread,
            current_volume=current_volume,
            avg_volume=avg_volume,
            time_of_day=time_of_day,
            session_high=session_high,
            session_low=session_low,
            atr=atr,
        )

        # Cache result (short TTL due to dynamic nature)
        signal_dict = signal.to_dict()
        signal_dict["_cache_hash"] = cache_hash
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.TIMING,
            signal=signal_dict,
            input_hash=cache_hash,
        )

        return signal

    @staticmethod
    def _fallback_analysis(
        ticker: str,
        current_price: float,
        action: str,
        vwap: float,
        time_of_day: str,
        spread_pct: float,
    ) -> TimingRecommendation:
        """Simple fallback timing analysis."""
        price_vs_vwap = ((current_price - vwap) / vwap) * 100 if vwap > 0 else 0

        # Determine time of day enum
        try:
            current_tod = TimeOfDay(time_of_day.lower().replace(" ", "_"))
        except ValueError:
            current_tod = TimeOfDay.MORNING

        # Simple timing logic
        wait_signals = []
        entry_signals = []

        # VWAP-based logic
        if action == "BUY":
            if price_vs_vwap > 1:
                wait_signals.append(f"Price {price_vs_vwap:.1f}% above VWAP")
                timing_action = TimingAction.WAIT_PULLBACK
                optimal_price = vwap
            elif price_vs_vwap < -1:
                entry_signals.append(f"Price {abs(price_vs_vwap):.1f}% below VWAP")
                timing_action = TimingAction.IMMEDIATE
                optimal_price = current_price
            else:
                timing_action = TimingAction.IMMEDIATE
                optimal_price = current_price
        else:  # SELL
            if price_vs_vwap < -1:
                wait_signals.append(f"Price {abs(price_vs_vwap):.1f}% below VWAP")
                timing_action = TimingAction.WAIT_BREAKOUT
                optimal_price = vwap
            else:
                timing_action = TimingAction.IMMEDIATE
                optimal_price = current_price

        # Time of day logic
        if current_tod == TimeOfDay.OPEN_VOLATILITY:
            wait_signals.append("First 30 minutes - high volatility")
            if timing_action == TimingAction.IMMEDIATE:
                timing_action = TimingAction.DEFER

        # Spread logic
        if spread_pct > 0.1:
            wait_signals.append(f"Wide spread: {spread_pct:.2f}%")

        # Score based on signals
        score = 50
        if len(entry_signals) > len(wait_signals):
            score = 70
        elif len(wait_signals) > len(entry_signals):
            score = 30

        return TimingRecommendation(
            action=timing_action,
            optimal_entry_price=optimal_price,
            entry_zone_low=optimal_price * 0.995,
            entry_zone_high=optimal_price * 1.005,
            time_recommendation="Wait for better entry if not urgent",
            current_time_of_day=current_tod,
            preferred_time_of_day=TimeOfDay.MORNING if current_tod == TimeOfDay.OPEN_VOLATILITY else None,
            vwap=vwap,
            price_vs_vwap=price_vs_vwap,
            vwap_recommendation=f"Price is {price_vs_vwap:+.1f}% vs VWAP",
            liquidity_score=70,
            spread_assessment="wide" if spread_pct > 0.1 else "normal",
            volume_assessment="normal",
            momentum_direction="neutral",
            momentum_strength=50,
            urgency=50,
            patience_reward=abs(price_vs_vwap) if price_vs_vwap > 0 else 0,
            entry_signals=entry_signals,
            wait_signals=wait_signals,
            score=score,
            confidence=40,
            reasoning=f"Fallback analysis: price is {price_vs_vwap:+.1f}% vs VWAP at {time_of_day}",
            provider="fallback",
        )
