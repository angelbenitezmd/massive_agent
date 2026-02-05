"""
Exit Strategy Agent - Optimal Exit Timing and Management.

This agent specializes in managing open positions and determining
when and how to exit trades for maximum profit or minimum loss.

Key responsibilities:
- Trailing stop recommendations
- Profit-taking levels
- Time-based exit rules
- Catalyst-based exits
- Scale-out strategies
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from app.services.llm_service import llm_service, LLMProvider
from app.services.agent_cache import agent_cache, AgentType

logger = logging.getLogger(__name__)


class ExitAction(Enum):
    """Recommended exit action."""
    HOLD = "hold"  # Continue holding
    MONITOR = "monitor"  # Same as hold - LLM sometimes returns this
    PARTIAL_EXIT = "partial_exit"  # Scale out
    FULL_EXIT = "full_exit"  # Close entire position
    TIGHTEN_STOP = "tighten_stop"  # Move stop loss closer
    TRAIL_STOP = "trail_stop"  # Implement trailing stop
    TAKE_PROFIT = "take_profit"  # Exit at current profit


class ExitUrgency(Enum):
    """Urgency of exit recommendation."""
    IMMEDIATE = "immediate"  # Exit now
    SOON = "soon"  # Exit today
    PLANNED = "planned"  # Exit at target
    MONITOR = "monitor"  # Watch for signals
    NONE = "none"  # No exit needed


@dataclass
class TrailingStopConfig:
    """Configuration for trailing stop."""
    enabled: bool
    type: str  # "percentage", "atr", "fixed"
    distance: float  # Distance from price
    activation_profit: float  # % profit before activation

    def to_dict(self) -> Dict:
        return {
            "enabled": self.enabled,
            "type": self.type,
            "distance": self.distance,
            "activation_profit": self.activation_profit,
        }


@dataclass
class ExitPlan:
    """Output from ExitStrategyAgent analysis."""
    action: ExitAction
    urgency: ExitUrgency

    stop_loss: float  # Current stop loss price
    take_profit_levels: List[float]  # Multiple profit targets
    trailing_stop: TrailingStopConfig

    partial_exit_percent: float  # % to exit if partial
    partial_exit_price: Optional[float]  # Price for partial exit

    time_exit_recommendation: Optional[str]  # Time-based exit rule
    days_held: int
    max_hold_days: int

    thesis_intact: bool  # Is original investment thesis still valid?
    thesis_concerns: List[str]  # Concerns about thesis

    exit_signals: List[str]  # Signals suggesting exit
    hold_signals: List[str]  # Signals suggesting hold

    score: float  # 0-100 (0=exit now, 100=strong hold)
    confidence: float

    reasoning: str = ""
    agent: str = "ExitStrategyAgent"
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "urgency": self.urgency.value,
            "stop_loss": self.stop_loss,
            "take_profit_levels": self.take_profit_levels,
            "trailing_stop": self.trailing_stop.to_dict(),
            "partial_exit_percent": self.partial_exit_percent,
            "partial_exit_price": self.partial_exit_price,
            "time_exit_recommendation": self.time_exit_recommendation,
            "days_held": self.days_held,
            "max_hold_days": self.max_hold_days,
            "thesis_intact": self.thesis_intact,
            "thesis_concerns": self.thesis_concerns,
            "exit_signals": self.exit_signals,
            "hold_signals": self.hold_signals,
            "score": self.score,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "agent": self.agent,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class ExitStrategyAgent:
    """
    Exit strategy and trade management agent.

    Uses Claude to determine:
    1. Whether to exit a position
    2. How to structure the exit (partial vs full)
    3. Stop loss and take profit placement
    4. Trailing stop configuration
    5. Time-based exit rules
    """

    SYSTEM_PROMPT = """You are a trade management specialist focused on exits.
Your job is to maximize profits and minimize losses through optimal exit timing.

You must assess:
1. **Current P&L**: Where does the position stand?
2. **Thesis Check**: Is the original investment thesis still valid?
3. **Technical Exit Signals**: Any bearish patterns or momentum shifts?
4. **Time Decay**: How long has this been held? Is there a time limit?
5. **Risk Management**: Should stops be tightened?
6. **Profit Taking**: When to lock in gains?

Exit principles:
- Let winners run, cut losers short
- Scale out of positions to lock in partial profits
- Use trailing stops to protect gains
- Exit if thesis changes, regardless of P&L
- Don't overstay in a trade
- ATR-based stops adapt to volatility

Return your analysis in JSON format."""

    @staticmethod
    async def analyze(
        ticker: str,
        position: Dict[str, Any],
        current_price: float,
        entry_price: float,
        entry_thesis: Optional[str],
        days_held: int,
        atr: float,
        technical_data: Dict[str, Any],
        news_sentiment: Optional[Dict] = None,
        original_catalyst: Optional[str] = None,
        original_stop_loss: Optional[float] = None,
        original_take_profit: Optional[float] = None,
    ) -> ExitPlan:
        """
        Analyze exit strategy for an open position.

        Args:
            ticker: Stock ticker
            position: Position details (qty, unrealized P&L, etc.)
            current_price: Current stock price
            entry_price: Entry price
            entry_thesis: Original reason for entry
            days_held: Number of days position has been held
            atr: Average True Range for volatility
            technical_data: Technical indicators
            news_sentiment: Current news sentiment
            original_catalyst: Catalyst that triggered entry
            original_stop_loss: Original stop loss price
            original_take_profit: Original take profit price

        Returns:
            ExitPlan with exit recommendations
        """
        qty = position.get("qty", 0)
        unrealized_pl = position.get("unrealized_pl", 0)
        unrealized_plpc = position.get("unrealized_plpc", 0) * 100 if position.get("unrealized_plpc") else 0

        # Calculate profit distance
        profit_pct = ((current_price - entry_price) / entry_price) * 100

        # Technical data formatting
        rsi = technical_data.get("rsi", 50)
        trend = technical_data.get("trend", "neutral")
        momentum = technical_data.get("momentum", "flat")
        sma_20 = technical_data.get("sma_20", current_price)
        sma_50 = technical_data.get("sma_50", current_price)

        user_prompt = f"""Analyze exit strategy for this position:

POSITION:
- Ticker: {ticker}
- Quantity: {qty} shares
- Entry Price: ${entry_price:.2f}
- Current Price: ${current_price:.2f}
- Unrealized P&L: ${unrealized_pl:+,.2f} ({unrealized_plpc:+.2f}%)
- Days Held: {days_held}

ORIGINAL TRADE SETUP:
- Entry Thesis: {entry_thesis or "Not recorded"}
- Original Catalyst: {original_catalyst or "Not recorded"}
- Original Stop Loss: {f"${original_stop_loss:.2f}" if original_stop_loss else "None set"}
- Original Take Profit: {f"${original_take_profit:.2f}" if original_take_profit else "None set"}

TECHNICAL DATA:
- RSI: {rsi:.1f}
- Trend: {trend}
- Momentum: {momentum}
- Price vs SMA 20: ${sma_20:.2f} ({((current_price-sma_20)/sma_20*100):+.1f}%)
- Price vs SMA 50: ${sma_50:.2f} ({((current_price-sma_50)/sma_50*100):+.1f}%)
- ATR (volatility): ${atr:.2f} ({(atr/current_price*100):.1f}%)

NEWS SENTIMENT:
{f"- Sentiment: {news_sentiment.get('sentiment', 'neutral')}" if news_sentiment else "No recent news"}
{f"- Score: {news_sentiment.get('score', 50)}" if news_sentiment else ""}

Provide your exit strategy in this JSON format:
{{
    "action": "hold" | "partial_exit" | "full_exit" | "tighten_stop" | "trail_stop" | "take_profit",
    "urgency": "immediate" | "soon" | "planned" | "monitor" | "none",
    "stop_loss": <recommended stop loss price>,
    "take_profit_levels": [<target 1>, <target 2>, <target 3>],
    "trailing_stop": {{
        "enabled": <true/false>,
        "type": "percentage" | "atr" | "fixed",
        "distance": <distance from price>,
        "activation_profit": <% profit to activate>
    }},
    "partial_exit_percent": <% to exit if partial, 0-100>,
    "partial_exit_price": <price for partial exit or null>,
    "time_exit_recommendation": "<time-based exit rule or null>",
    "max_hold_days": <maximum days to hold>,
    "thesis_intact": <true if original thesis is still valid>,
    "thesis_concerns": ["<concerns about the thesis>"],
    "exit_signals": ["<signals suggesting exit>"],
    "hold_signals": ["<signals suggesting hold>"],
    "score": <0-100, where 0=exit immediately, 100=strong hold>,
    "confidence": <0-100>,
    "reasoning": "<2-3 sentence exit strategy recommendation>"
}}"""

        result = await llm_service.analyze(
            system_prompt=ExitStrategyAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.2
        )

        if result.get("error"):
            logger.warning(f"ExitStrategyAgent error: {result['error']}")
            return ExitStrategyAgent._fallback_analysis(
                ticker, current_price, entry_price, days_held, atr, unrealized_plpc
            )

        # Parse result into ExitPlan
        try:
            trailing_data = result.get("trailing_stop", {})
            return ExitPlan(
                action=ExitAction(result.get("action", "hold")),
                urgency=ExitUrgency(result.get("urgency", "none")),
                stop_loss=float(result.get("stop_loss", entry_price * 0.95)),
                take_profit_levels=result.get("take_profit_levels", []),
                trailing_stop=TrailingStopConfig(
                    enabled=trailing_data.get("enabled", False),
                    type=trailing_data.get("type", "percentage"),
                    distance=float(trailing_data.get("distance", 2)),
                    activation_profit=float(trailing_data.get("activation_profit", 5)),
                ),
                partial_exit_percent=float(result.get("partial_exit_percent", 0)),
                partial_exit_price=result.get("partial_exit_price"),
                time_exit_recommendation=result.get("time_exit_recommendation"),
                days_held=days_held,
                max_hold_days=int(result.get("max_hold_days", 30)),
                thesis_intact=result.get("thesis_intact", True),
                thesis_concerns=result.get("thesis_concerns", []),
                exit_signals=result.get("exit_signals", []),
                hold_signals=result.get("hold_signals", []),
                score=float(result.get("score", 50)),
                confidence=float(result.get("confidence", 50)),
                reasoning=result.get("reasoning", ""),
                provider=result.get("provider", "claude"),
            )
        except Exception as e:
            logger.error(f"Error parsing ExitStrategyAgent result: {e}")
            return ExitStrategyAgent._fallback_analysis(
                ticker, current_price, entry_price, days_held, atr, unrealized_plpc
            )

    @staticmethod
    async def analyze_with_cache(
        ticker: str,
        position: Dict[str, Any],
        current_price: float,
        entry_price: float,
        entry_thesis: Optional[str],
        days_held: int,
        atr: float,
        technical_data: Dict[str, Any],
        news_sentiment: Optional[Dict] = None,
        original_catalyst: Optional[str] = None,
        original_stop_loss: Optional[float] = None,
        original_take_profit: Optional[float] = None,
        force: bool = False,
    ) -> ExitPlan:
        """
        Exit strategy analysis with caching.

        Exit strategy changes with price, so cache has short TTL.
        """
        ticker = ticker.upper()

        # Cache key includes price bucket (round to nearest 0.5%)
        price_bucket = round((current_price / entry_price - 1) * 200) / 2
        cache_hash = agent_cache._hash_data({
            "ticker": ticker,
            "price_bucket": price_bucket,
            "days_held": days_held,
        })

        if not force:
            cached = agent_cache.get_cached_signal(ticker, AgentType.EXIT)
            if cached and cached.get("_cache_hash") == cache_hash:
                logger.info(f"ExitStrategyAgent for {ticker}: Using cached result")
                try:
                    trailing_data = cached.get("trailing_stop", {})
                    return ExitPlan(
                        action=ExitAction(cached.get("action", "hold")),
                        urgency=ExitUrgency(cached.get("urgency", "none")),
                        stop_loss=cached.get("stop_loss", entry_price * 0.95),
                        take_profit_levels=cached.get("take_profit_levels", []),
                        trailing_stop=TrailingStopConfig(
                            enabled=trailing_data.get("enabled", False),
                            type=trailing_data.get("type", "percentage"),
                            distance=trailing_data.get("distance", 2),
                            activation_profit=trailing_data.get("activation_profit", 5),
                        ),
                        partial_exit_percent=cached.get("partial_exit_percent", 0),
                        partial_exit_price=cached.get("partial_exit_price"),
                        time_exit_recommendation=cached.get("time_exit_recommendation"),
                        days_held=days_held,
                        max_hold_days=cached.get("max_hold_days", 30),
                        thesis_intact=cached.get("thesis_intact", True),
                        thesis_concerns=cached.get("thesis_concerns", []),
                        exit_signals=cached.get("exit_signals", []),
                        hold_signals=cached.get("hold_signals", []),
                        score=cached.get("score", 50),
                        confidence=cached.get("confidence", 50),
                        reasoning=cached.get("reasoning", ""),
                        provider="cache",
                    )
                except Exception:
                    pass

        # Run analysis
        logger.info(f"ExitStrategyAgent for {ticker}: Running LLM analysis")
        signal = await ExitStrategyAgent.analyze(
            ticker=ticker,
            position=position,
            current_price=current_price,
            entry_price=entry_price,
            entry_thesis=entry_thesis,
            days_held=days_held,
            atr=atr,
            technical_data=technical_data,
            news_sentiment=news_sentiment,
            original_catalyst=original_catalyst,
            original_stop_loss=original_stop_loss,
            original_take_profit=original_take_profit,
        )

        # Cache result
        signal_dict = signal.to_dict()
        signal_dict["_cache_hash"] = cache_hash
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.EXIT,
            signal=signal_dict,
            input_hash=cache_hash,
        )

        return signal

    @staticmethod
    def _fallback_analysis(
        ticker: str,
        current_price: float,
        entry_price: float,
        days_held: int,
        atr: float,
        unrealized_plpc: float,
    ) -> ExitPlan:
        """Simple fallback exit analysis."""
        profit_pct = ((current_price - entry_price) / entry_price) * 100

        # Default action based on profit
        if profit_pct < -5:
            action = ExitAction.TIGHTEN_STOP
            urgency = ExitUrgency.SOON
            score = 30
        elif profit_pct > 10:
            action = ExitAction.PARTIAL_EXIT
            urgency = ExitUrgency.PLANNED
            score = 60
        else:
            action = ExitAction.HOLD
            urgency = ExitUrgency.MONITOR
            score = 70

        # Simple stop loss (2 ATR below current price or entry - 5%)
        stop_loss = max(current_price - 2 * atr, entry_price * 0.95)

        # Simple take profit levels
        take_profit_levels = [
            entry_price * 1.05,  # 5%
            entry_price * 1.10,  # 10%
            entry_price * 1.15,  # 15%
        ]

        return ExitPlan(
            action=action,
            urgency=urgency,
            stop_loss=stop_loss,
            take_profit_levels=take_profit_levels,
            trailing_stop=TrailingStopConfig(
                enabled=profit_pct > 5,
                type="percentage",
                distance=3.0,
                activation_profit=5.0,
            ),
            partial_exit_percent=50 if action == ExitAction.PARTIAL_EXIT else 0,
            partial_exit_price=current_price if action == ExitAction.PARTIAL_EXIT else None,
            time_exit_recommendation=None,
            days_held=days_held,
            max_hold_days=30,
            thesis_intact=True,
            thesis_concerns=["Fallback analysis has limited data"],
            exit_signals=[f"Position at {profit_pct:+.1f}%"] if profit_pct < -3 else [],
            hold_signals=[f"Position at {profit_pct:+.1f}%"] if profit_pct > 0 else [],
            score=score,
            confidence=40,
            reasoning=f"Fallback analysis: position at {profit_pct:+.1f}% after {days_held} days",
            provider="fallback",
        )
