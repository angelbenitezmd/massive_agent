"""
Risk Management Agent - Portfolio-Level Risk Analysis.

This agent evaluates portfolio-level risk and provides position sizing recommendations.
It has VETO power in the debate system to block trades that are too risky.

Key responsibilities:
- Portfolio correlation analysis
- Sector concentration warnings
- Position sizing recommendations
- Drawdown risk assessment
- Volatility-adjusted sizing
- Circuit breaker conditions
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from app.services.llm_service import llm_service, LLMProvider
from app.services.agent_cache import agent_cache, AgentType

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Overall risk level assessment."""
    EXTREME = "extreme"  # Do not trade
    HIGH = "high"  # Reduce position size
    ELEVATED = "elevated"  # Proceed with caution
    NORMAL = "normal"  # Standard trading
    LOW = "low"  # Favorable conditions


class PositionSizeRecommendation(Enum):
    """Position sizing recommendation."""
    ZERO = "zero"  # Do not enter
    MINIMAL = "minimal"  # 25% of normal
    REDUCED = "reduced"  # 50% of normal
    STANDARD = "standard"  # Normal size
    INCREASED = "increased"  # 150% of normal


@dataclass
class RiskAssessment:
    """Output from RiskManagementAgent analysis."""
    risk_level: RiskLevel
    veto: bool  # True = block the trade
    veto_reason: Optional[str]

    position_size_recommendation: PositionSizeRecommendation
    max_position_percent: float  # Max % of portfolio
    suggested_shares: int
    max_dollar_amount: float

    portfolio_correlation: float  # 0-1, correlation with existing positions
    sector_concentration: float  # 0-1, sector concentration level
    volatility_adjusted_size: float  # Position size adjusted for volatility

    drawdown_risk: float  # 0-100, estimated max drawdown
    daily_var: float  # Value at Risk (1-day)

    warnings: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)

    score: float = 50  # 0-100 (0=extreme risk, 100=very safe)
    confidence: float = 50

    reasoning: str = ""
    agent: str = "RiskManagementAgent"
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level.value,
            "veto": self.veto,
            "veto_reason": self.veto_reason,
            "position_size_recommendation": self.position_size_recommendation.value,
            "max_position_percent": self.max_position_percent,
            "suggested_shares": self.suggested_shares,
            "max_dollar_amount": self.max_dollar_amount,
            "portfolio_correlation": self.portfolio_correlation,
            "sector_concentration": self.sector_concentration,
            "volatility_adjusted_size": self.volatility_adjusted_size,
            "drawdown_risk": self.drawdown_risk,
            "daily_var": self.daily_var,
            "warnings": self.warnings,
            "risk_factors": self.risk_factors,
            "mitigations": self.mitigations,
            "score": self.score,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "agent": self.agent,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class RiskManagementAgent:
    """
    Portfolio risk analysis agent with VETO power.

    Uses Claude to evaluate:
    1. Portfolio-level risk exposure
    2. Correlation with existing positions
    3. Sector concentration
    4. Volatility-adjusted position sizing
    5. Circuit breaker conditions

    This agent can VETO trades that are too risky.
    """

    SYSTEM_PROMPT = """You are a chief risk officer at a quantitative trading firm.
Your PRIMARY responsibility is to PROTECT CAPITAL. You have VETO power over any trade.

You must evaluate:
1. **Position Sizing**: What is the appropriate position size given risk?
2. **Portfolio Correlation**: How correlated is this with existing positions?
3. **Sector Concentration**: Are we too concentrated in one sector?
4. **Volatility**: How volatile is this stock? Adjust size accordingly.
5. **Drawdown Risk**: What is the maximum potential loss?
6. **Circuit Breaker**: Should trading be halted?

Risk rules (MUST follow):
- Never risk more than 2% of portfolio on a single trade
- Never allocate more than 10% of portfolio to a single position
- Reduce size if correlation with existing positions > 0.7
- Reduce size if sector concentration > 30%
- VETO if daily drawdown > 5%
- VETO if VaR exceeds comfort level

Be CONSERVATIVE. Capital preservation is paramount.
Return your analysis in JSON format."""

    @staticmethod
    async def analyze(
        ticker: str,
        proposed_action: str,
        proposed_quantity: int,
        current_price: float,
        ticker_volatility: float,
        current_positions: List[Dict],
        account: Dict,
        daily_pnl: Optional[float] = None,
        sector: Optional[str] = None,
        correlation_data: Optional[Dict] = None,
        vix_level: Optional[float] = None,
    ) -> RiskAssessment:
        """
        Evaluate portfolio risk for a proposed trade.

        Args:
            ticker: Stock ticker
            proposed_action: BUY or SELL
            proposed_quantity: Proposed number of shares
            current_price: Current stock price
            ticker_volatility: Stock's historical volatility (std dev)
            current_positions: List of current positions
            account: Account info (equity, buying power, etc.)
            daily_pnl: Today's P&L
            sector: Stock's sector
            correlation_data: Correlation with other holdings
            vix_level: Current VIX

        Returns:
            RiskAssessment with position sizing and veto decision
        """
        portfolio_value = float(account.get("equity", account.get("portfolio_value", 100000)))
        buying_power = float(account.get("buying_power", portfolio_value * 0.5))
        proposed_value = proposed_quantity * current_price

        # Format current positions
        positions_text = ""
        total_position_value = 0
        sector_exposure = {}

        for pos in current_positions:
            symbol = pos.get("symbol", "")
            qty = pos.get("qty", 0)
            market_value = pos.get("market_value", 0)
            pos_sector = pos.get("sector", "Unknown")
            unrealized_pl = pos.get("unrealized_pl", 0)

            total_position_value += market_value
            sector_exposure[pos_sector] = sector_exposure.get(pos_sector, 0) + market_value

            positions_text += f"- {symbol}: {qty} shares, ${market_value:,.0f}, P&L: ${unrealized_pl:+,.0f}\n"

        if not positions_text:
            positions_text = "No current positions"

        # Format sector exposure
        sector_text = "\n".join(
            f"- {s}: ${v:,.0f} ({v/portfolio_value*100:.1f}%)"
            for s, v in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)
        ) if sector_exposure else "No sector exposure data"

        user_prompt = f"""Evaluate risk for this proposed trade:

PROPOSED TRADE:
- Ticker: {ticker}
- Action: {proposed_action}
- Quantity: {proposed_quantity} shares
- Price: ${current_price:.2f}
- Value: ${proposed_value:,.0f}
- Sector: {sector or "Unknown"}
- Volatility (std dev): {ticker_volatility:.2f}%

ACCOUNT:
- Portfolio Value: ${portfolio_value:,.0f}
- Buying Power: ${buying_power:,.0f}
- Daily P&L: ${daily_pnl:+,.0f if daily_pnl else "N/A"}
- Daily P&L %: {(daily_pnl/portfolio_value*100) if daily_pnl else "N/A":.2f}%

CURRENT POSITIONS:
{positions_text}

SECTOR EXPOSURE:
{sector_text}

MARKET CONDITIONS:
- VIX: {vix_level:.1f if vix_level else "N/A"}

CORRELATION DATA:
{correlation_data or "Not available"}

Evaluate risk and provide position sizing in this JSON format:
{{
    "risk_level": "extreme" | "high" | "elevated" | "normal" | "low",
    "veto": <true if trade should be blocked, false otherwise>,
    "veto_reason": "<reason for veto, or null>",
    "position_size_recommendation": "zero" | "minimal" | "reduced" | "standard" | "increased",
    "max_position_percent": <max % of portfolio for this position>,
    "suggested_shares": <recommended number of shares>,
    "max_dollar_amount": <max dollar amount to allocate>,
    "portfolio_correlation": <0-1 correlation estimate>,
    "sector_concentration": <0-1 concentration level>,
    "volatility_adjusted_size": <volatility-adjusted position size in $>,
    "drawdown_risk": <0-100 estimated max drawdown %>,
    "daily_var": <value at risk in $>,
    "warnings": ["<list of risk warnings>"],
    "risk_factors": ["<list of risk factors>"],
    "mitigations": ["<suggested risk mitigations>"],
    "score": <0-100, where 0=extreme risk, 100=very safe>,
    "confidence": <0-100>,
    "reasoning": "<2-3 sentence risk assessment>"
}}"""

        result = await llm_service.analyze(
            system_prompt=RiskManagementAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.1  # Low temperature for conservative, consistent risk assessment
        )

        if result.get("error"):
            logger.warning(f"RiskManagementAgent error: {result['error']}")
            return RiskManagementAgent._fallback_analysis(
                ticker, proposed_action, proposed_quantity, current_price,
                ticker_volatility, portfolio_value, daily_pnl
            )

        # Parse result into RiskAssessment
        try:
            return RiskAssessment(
                risk_level=RiskLevel(result.get("risk_level", "normal")),
                veto=result.get("veto", False),
                veto_reason=result.get("veto_reason"),
                position_size_recommendation=PositionSizeRecommendation(
                    result.get("position_size_recommendation", "standard")
                ),
                max_position_percent=float(result.get("max_position_percent", 5)),
                suggested_shares=int(result.get("suggested_shares", proposed_quantity)),
                max_dollar_amount=float(result.get("max_dollar_amount", proposed_value)),
                portfolio_correlation=float(result.get("portfolio_correlation", 0.5)),
                sector_concentration=float(result.get("sector_concentration", 0.3)),
                volatility_adjusted_size=float(result.get("volatility_adjusted_size", proposed_value)),
                drawdown_risk=float(result.get("drawdown_risk", 10)),
                daily_var=float(result.get("daily_var", proposed_value * 0.05)),
                warnings=result.get("warnings", []),
                risk_factors=result.get("risk_factors", []),
                mitigations=result.get("mitigations", []),
                score=float(result.get("score", 50)),
                confidence=float(result.get("confidence", 50)),
                reasoning=result.get("reasoning", ""),
                provider=result.get("provider", "claude"),
            )
        except Exception as e:
            logger.error(f"Error parsing RiskManagementAgent result: {e}")
            return RiskManagementAgent._fallback_analysis(
                ticker, proposed_action, proposed_quantity, current_price,
                ticker_volatility, portfolio_value, daily_pnl
            )

    @staticmethod
    async def analyze_with_cache(
        ticker: str,
        proposed_action: str,
        proposed_quantity: int,
        current_price: float,
        ticker_volatility: float,
        current_positions: List[Dict],
        account: Dict,
        daily_pnl: Optional[float] = None,
        sector: Optional[str] = None,
        correlation_data: Optional[Dict] = None,
        vix_level: Optional[float] = None,
        force: bool = False,
    ) -> RiskAssessment:
        """
        Risk analysis with caching.

        Risk assessment changes with positions and account, so cache key includes these.
        """
        ticker = ticker.upper()

        # Risk changes with portfolio state, so use shorter TTL and more specific cache key
        cache_hash = agent_cache._hash_data({
            "ticker": ticker,
            "action": proposed_action,
            "qty": proposed_quantity,
            "positions": len(current_positions),
            "equity": round(account.get("equity", 0), -2),  # Round to nearest 100
        })

        if not force:
            cached = agent_cache.get_cached_signal(ticker, AgentType.RISK)
            if cached and cached.get("_cache_hash") == cache_hash:
                logger.info(f"RiskManagementAgent for {ticker}: Using cached result")
                try:
                    return RiskAssessment(
                        risk_level=RiskLevel(cached.get("risk_level", "normal")),
                        veto=cached.get("veto", False),
                        veto_reason=cached.get("veto_reason"),
                        position_size_recommendation=PositionSizeRecommendation(
                            cached.get("position_size_recommendation", "standard")
                        ),
                        max_position_percent=cached.get("max_position_percent", 5),
                        suggested_shares=cached.get("suggested_shares", proposed_quantity),
                        max_dollar_amount=cached.get("max_dollar_amount", 0),
                        portfolio_correlation=cached.get("portfolio_correlation", 0.5),
                        sector_concentration=cached.get("sector_concentration", 0.3),
                        volatility_adjusted_size=cached.get("volatility_adjusted_size", 0),
                        drawdown_risk=cached.get("drawdown_risk", 10),
                        daily_var=cached.get("daily_var", 0),
                        warnings=cached.get("warnings", []),
                        risk_factors=cached.get("risk_factors", []),
                        mitigations=cached.get("mitigations", []),
                        score=cached.get("score", 50),
                        confidence=cached.get("confidence", 50),
                        reasoning=cached.get("reasoning", ""),
                        provider="cache",
                    )
                except Exception:
                    pass

        # Run analysis
        logger.info(f"RiskManagementAgent for {ticker}: Running LLM analysis")
        signal = await RiskManagementAgent.analyze(
            ticker=ticker,
            proposed_action=proposed_action,
            proposed_quantity=proposed_quantity,
            current_price=current_price,
            ticker_volatility=ticker_volatility,
            current_positions=current_positions,
            account=account,
            daily_pnl=daily_pnl,
            sector=sector,
            correlation_data=correlation_data,
            vix_level=vix_level,
        )

        # Cache result
        signal_dict = signal.to_dict()
        signal_dict["_cache_hash"] = cache_hash
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.RISK,
            signal=signal_dict,
            input_hash=cache_hash,
        )

        return signal

    @staticmethod
    def _fallback_analysis(
        ticker: str,
        proposed_action: str,
        proposed_quantity: int,
        current_price: float,
        ticker_volatility: float,
        portfolio_value: float,
        daily_pnl: Optional[float],
    ) -> RiskAssessment:
        """Simple fallback risk analysis."""
        proposed_value = proposed_quantity * current_price
        position_percent = (proposed_value / portfolio_value) * 100

        # Basic risk checks
        veto = False
        veto_reason = None
        warnings = []
        risk_level = RiskLevel.NORMAL

        # Check position size
        if position_percent > 10:
            veto = True
            veto_reason = f"Position size ({position_percent:.1f}%) exceeds 10% limit"
            risk_level = RiskLevel.EXTREME
        elif position_percent > 5:
            warnings.append(f"Large position: {position_percent:.1f}% of portfolio")
            risk_level = RiskLevel.ELEVATED

        # Check daily drawdown
        if daily_pnl and portfolio_value:
            daily_pnl_pct = (daily_pnl / portfolio_value) * 100
            if daily_pnl_pct < -5:
                veto = True
                veto_reason = f"Daily drawdown ({daily_pnl_pct:.1f}%) exceeds 5% limit"
                risk_level = RiskLevel.EXTREME
            elif daily_pnl_pct < -2:
                warnings.append(f"Significant daily loss: {daily_pnl_pct:.1f}%")
                risk_level = RiskLevel.HIGH

        # Check volatility
        if ticker_volatility > 5:  # High volatility stock
            warnings.append(f"High volatility stock: {ticker_volatility:.1f}%")
            if risk_level == RiskLevel.NORMAL:
                risk_level = RiskLevel.ELEVATED

        # Position sizing
        if veto:
            size_rec = PositionSizeRecommendation.ZERO
            suggested_shares = 0
        elif risk_level == RiskLevel.HIGH:
            size_rec = PositionSizeRecommendation.MINIMAL
            suggested_shares = int(proposed_quantity * 0.25)
        elif risk_level == RiskLevel.ELEVATED:
            size_rec = PositionSizeRecommendation.REDUCED
            suggested_shares = int(proposed_quantity * 0.5)
        else:
            size_rec = PositionSizeRecommendation.STANDARD
            suggested_shares = proposed_quantity

        # Simple VaR estimate (5% of position value)
        daily_var = proposed_value * 0.05

        # Score based on risk level
        score_map = {
            RiskLevel.EXTREME: 10,
            RiskLevel.HIGH: 30,
            RiskLevel.ELEVATED: 50,
            RiskLevel.NORMAL: 70,
            RiskLevel.LOW: 90,
        }

        return RiskAssessment(
            risk_level=risk_level,
            veto=veto,
            veto_reason=veto_reason,
            position_size_recommendation=size_rec,
            max_position_percent=min(10, 5 - ticker_volatility * 0.5),
            suggested_shares=suggested_shares,
            max_dollar_amount=portfolio_value * 0.1,
            portfolio_correlation=0.5,  # Default
            sector_concentration=0.3,  # Default
            volatility_adjusted_size=proposed_value * (2 / max(1, ticker_volatility)),
            drawdown_risk=ticker_volatility * 2,
            daily_var=daily_var,
            warnings=warnings,
            risk_factors=["Fallback analysis - limited data"],
            mitigations=["Use stop loss", "Reduce position size if uncertain"],
            score=score_map.get(risk_level, 50),
            confidence=40,
            reasoning=f"Fallback risk analysis: position is {position_percent:.1f}% of portfolio with {ticker_volatility:.1f}% volatility",
            provider="fallback",
        )
