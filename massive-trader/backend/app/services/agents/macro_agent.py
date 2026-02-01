"""
Macro Agent - Market Regime Detection and Macro Analysis.

Analyzes macro-economic conditions and market regime to inform trading decisions.
Focuses on:
- Market regime detection (bull/bear/sideways/volatile)
- VIX and fear/greed analysis
- Sector rotation signals
- Fed policy impact
- Cross-market correlations
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from app.services.llm_service import llm_service, LLMProvider
from app.services.agent_cache import agent_cache, AgentType

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    RISK_OFF = "risk_off"
    RISK_ON = "risk_on"


class RiskEnvironment(Enum):
    """Risk environment states."""
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"
    TRANSITIONING = "transitioning"


@dataclass
class MacroSignal:
    """Output from MacroAgent analysis."""
    regime: MarketRegime
    regime_confidence: float  # 0-100
    risk_environment: RiskEnvironment
    vix_assessment: str  # "low", "normal", "elevated", "extreme"

    sector_preferences: List[str]  # Preferred sectors in current regime
    sectors_to_avoid: List[str]  # Sectors to avoid

    trend_strength: str  # "strong", "moderate", "weak"
    trend_direction: str  # "up", "down", "flat"

    fed_impact: str  # "hawkish", "dovish", "neutral"
    liquidity_conditions: str  # "tight", "normal", "loose"

    score: float  # 0-100 overall macro score (>50 = favorable)
    confidence: float  # 0-100

    key_factors: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)

    reasoning: str = ""
    agent: str = "MacroAgent"
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "regime_confidence": self.regime_confidence,
            "risk_environment": self.risk_environment.value,
            "vix_assessment": self.vix_assessment,
            "sector_preferences": self.sector_preferences,
            "sectors_to_avoid": self.sectors_to_avoid,
            "trend_strength": self.trend_strength,
            "trend_direction": self.trend_direction,
            "fed_impact": self.fed_impact,
            "liquidity_conditions": self.liquidity_conditions,
            "score": self.score,
            "confidence": self.confidence,
            "key_factors": self.key_factors,
            "risks": self.risks,
            "opportunities": self.opportunities,
            "reasoning": self.reasoning,
            "agent": self.agent,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class MacroAgent:
    """
    Macro-economic and market regime analysis agent.

    Uses Claude to analyze market-wide conditions and determine:
    1. Current market regime (bull/bear/sideways/volatile)
    2. Risk-on vs risk-off environment
    3. Sector rotation opportunities
    4. Fed policy implications
    """

    SYSTEM_PROMPT = """You are a senior macro strategist at a global macro hedge fund.
Your job is to analyze market-wide conditions and determine the current trading environment.

You must assess:
1. **Market Regime**: Is this a bull market, bear market, sideways consolidation, or high volatility?
2. **Risk Environment**: Are investors in risk-on mode (seeking growth) or risk-off mode (seeking safety)?
3. **VIX/Volatility**: Is volatility low, normal, elevated, or extreme?
4. **Sector Rotation**: Which sectors are leading? Which are lagging?
5. **Fed/Monetary Policy**: Hawkish, dovish, or neutral stance?
6. **Liquidity**: Are liquidity conditions tight, normal, or loose?

Key indicators to consider:
- VIX level and trend (< 15 = low, 15-20 = normal, 20-30 = elevated, > 30 = extreme)
- SPY/QQQ trend vs 50-day and 200-day moving averages
- Sector ETF performance (XLF, XLK, XLE, XLV, XLU, etc.)
- Credit spreads (widening = risk-off, tightening = risk-on)
- Dollar strength (DXY)
- Treasury yields

Be decisive and provide actionable guidance for traders.
Return your analysis in JSON format."""

    @staticmethod
    async def analyze(
        vix_level: float,
        spy_data: Dict[str, Any],
        sector_performance: Dict[str, float],
        fed_commentary: Optional[str] = None,
        treasury_yields: Optional[Dict[str, float]] = None,
        dollar_index: Optional[float] = None,
    ) -> MacroSignal:
        """
        Analyze macro conditions using Claude.

        Args:
            vix_level: Current VIX level
            spy_data: SPY price data with MAs and trend
            sector_performance: Dict of sector -> % change
            fed_commentary: Recent Fed commentary if available
            treasury_yields: Dict of yield curve data
            dollar_index: DXY value

        Returns:
            MacroSignal with regime and recommendations
        """
        # Build the analysis prompt
        sector_text = "\n".join(
            f"- {sector}: {perf:+.2f}%"
            for sector, perf in sorted(
                sector_performance.items(),
                key=lambda x: x[1],
                reverse=True
            )
        ) if sector_performance else "No sector data available"

        spy_text = f"""
- Current Price: ${spy_data.get('price', 0):.2f}
- vs SMA 50: {spy_data.get('vs_sma50', 'N/A')}
- vs SMA 200: {spy_data.get('vs_sma200', 'N/A')}
- 5-Day Change: {spy_data.get('change_5d', 0):+.2f}%
- 20-Day Change: {spy_data.get('change_20d', 0):+.2f}%
- Trend: {spy_data.get('trend', 'unknown')}
""" if spy_data else "No SPY data available"

        yields_text = ""
        if treasury_yields:
            yields_text = "\n".join(
                f"- {maturity}: {rate:.2f}%"
                for maturity, rate in treasury_yields.items()
            )

        user_prompt = f"""Analyze current macro conditions:

VIX LEVEL: {vix_level:.2f}

SPY (S&P 500) DATA:
{spy_text}

SECTOR PERFORMANCE (recent):
{sector_text}

{f"DOLLAR INDEX (DXY): {dollar_index:.2f}" if dollar_index else ""}

{f"TREASURY YIELDS:\n{yields_text}" if yields_text else ""}

{f"FED COMMENTARY:\n{fed_commentary}" if fed_commentary else ""}

Provide your analysis in this JSON format:
{{
    "regime": "bull" | "bear" | "sideways" | "volatile",
    "regime_confidence": <0-100>,
    "risk_environment": "risk_on" | "risk_off" | "neutral" | "transitioning",
    "vix_assessment": "low" | "normal" | "elevated" | "extreme",
    "sector_preferences": ["<sectors to favor>"],
    "sectors_to_avoid": ["<sectors to avoid>"],
    "trend_strength": "strong" | "moderate" | "weak",
    "trend_direction": "up" | "down" | "flat",
    "fed_impact": "hawkish" | "dovish" | "neutral",
    "liquidity_conditions": "tight" | "normal" | "loose",
    "score": <0-100, where 50 is neutral, >70 = very favorable for longs>,
    "confidence": <0-100>,
    "key_factors": ["<list of key factors driving your view>"],
    "risks": ["<list of macro risks>"],
    "opportunities": ["<list of opportunities>"],
    "reasoning": "<2-3 sentence summary of your view>"
}}"""

        result = await llm_service.analyze(
            system_prompt=MacroAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.2
        )

        if result.get("error"):
            logger.warning(f"MacroAgent error: {result['error']}")
            return MacroAgent._fallback_analysis(vix_level, spy_data, sector_performance)

        # Parse result into MacroSignal
        try:
            return MacroSignal(
                regime=MarketRegime(result.get("regime", "sideways")),
                regime_confidence=float(result.get("regime_confidence", 50)),
                risk_environment=RiskEnvironment(result.get("risk_environment", "neutral")),
                vix_assessment=result.get("vix_assessment", "normal"),
                sector_preferences=result.get("sector_preferences", []),
                sectors_to_avoid=result.get("sectors_to_avoid", []),
                trend_strength=result.get("trend_strength", "moderate"),
                trend_direction=result.get("trend_direction", "flat"),
                fed_impact=result.get("fed_impact", "neutral"),
                liquidity_conditions=result.get("liquidity_conditions", "normal"),
                score=float(result.get("score", 50)),
                confidence=float(result.get("confidence", 50)),
                key_factors=result.get("key_factors", []),
                risks=result.get("risks", []),
                opportunities=result.get("opportunities", []),
                reasoning=result.get("reasoning", ""),
                provider=result.get("provider", "claude"),
            )
        except Exception as e:
            logger.error(f"Error parsing MacroAgent result: {e}")
            return MacroAgent._fallback_analysis(vix_level, spy_data, sector_performance)

    @staticmethod
    async def analyze_with_cache(
        vix_level: float,
        spy_data: Dict[str, Any],
        sector_performance: Dict[str, float],
        fed_commentary: Optional[str] = None,
        treasury_yields: Optional[Dict[str, float]] = None,
        dollar_index: Optional[float] = None,
        force: bool = False,
    ) -> MacroSignal:
        """
        Analyze macro conditions with caching.

        Macro conditions change slowly, so cache aggressively (5 minute TTL).
        """
        cache_key = "MACRO_GLOBAL"  # Global macro, not per-ticker

        # Check cache (macro changes slowly, use longer TTL)
        if not force:
            cached = agent_cache.get_cached_signal(cache_key, AgentType.MACRO)
            if cached:
                logger.info("MacroAgent: Using cached result")
                # Convert cached dict back to MacroSignal
                try:
                    return MacroSignal(
                        regime=MarketRegime(cached.get("regime", "sideways")),
                        regime_confidence=cached.get("regime_confidence", 50),
                        risk_environment=RiskEnvironment(cached.get("risk_environment", "neutral")),
                        vix_assessment=cached.get("vix_assessment", "normal"),
                        sector_preferences=cached.get("sector_preferences", []),
                        sectors_to_avoid=cached.get("sectors_to_avoid", []),
                        trend_strength=cached.get("trend_strength", "moderate"),
                        trend_direction=cached.get("trend_direction", "flat"),
                        fed_impact=cached.get("fed_impact", "neutral"),
                        liquidity_conditions=cached.get("liquidity_conditions", "normal"),
                        score=cached.get("score", 50),
                        confidence=cached.get("confidence", 50),
                        key_factors=cached.get("key_factors", []),
                        risks=cached.get("risks", []),
                        opportunities=cached.get("opportunities", []),
                        reasoning=cached.get("reasoning", ""),
                        provider=cached.get("provider", "cache"),
                    )
                except Exception:
                    pass  # Fall through to new analysis

        # Run analysis
        logger.info("MacroAgent: Running LLM analysis")
        signal = await MacroAgent.analyze(
            vix_level=vix_level,
            spy_data=spy_data,
            sector_performance=sector_performance,
            fed_commentary=fed_commentary,
            treasury_yields=treasury_yields,
            dollar_index=dollar_index,
        )

        # Cache result
        agent_cache.set_cached_signal(
            ticker=cache_key,
            agent_type=AgentType.MACRO,
            signal=signal.to_dict(),
            input_hash=agent_cache._hash_data({
                "vix": round(vix_level, 1),
                "spy_trend": spy_data.get("trend") if spy_data else None,
            }),
        )

        return signal

    @staticmethod
    def _fallback_analysis(
        vix_level: float,
        spy_data: Dict[str, Any],
        sector_performance: Dict[str, float],
    ) -> MacroSignal:
        """Simple fallback analysis without LLM."""
        # Determine regime from VIX and SPY trend
        if vix_level >= 30:
            regime = MarketRegime.VOLATILE
            risk_env = RiskEnvironment.RISK_OFF
        elif vix_level >= 20:
            regime = MarketRegime.BEAR if spy_data.get("trend") == "down" else MarketRegime.SIDEWAYS
            risk_env = RiskEnvironment.RISK_OFF
        elif vix_level >= 15:
            regime = MarketRegime.SIDEWAYS
            risk_env = RiskEnvironment.NEUTRAL
        else:
            regime = MarketRegime.BULL if spy_data.get("trend") == "up" else MarketRegime.SIDEWAYS
            risk_env = RiskEnvironment.RISK_ON

        # VIX assessment
        if vix_level < 15:
            vix_assessment = "low"
        elif vix_level < 20:
            vix_assessment = "normal"
        elif vix_level < 30:
            vix_assessment = "elevated"
        else:
            vix_assessment = "extreme"

        # Simple score
        score = 50
        if regime == MarketRegime.BULL:
            score = 70
        elif regime == MarketRegime.BEAR:
            score = 30
        elif regime == MarketRegime.VOLATILE:
            score = 35

        return MacroSignal(
            regime=regime,
            regime_confidence=60,
            risk_environment=risk_env,
            vix_assessment=vix_assessment,
            sector_preferences=[],
            sectors_to_avoid=[],
            trend_strength="moderate",
            trend_direction=spy_data.get("trend", "flat") if spy_data else "flat",
            fed_impact="neutral",
            liquidity_conditions="normal",
            score=score,
            confidence=50,
            key_factors=[f"VIX at {vix_level:.1f}"],
            risks=["Fallback analysis - limited data"],
            opportunities=[],
            reasoning="Fallback analysis based on VIX and SPY trend only",
            provider="fallback",
        )
