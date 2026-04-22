"""Risk management engine for trade evaluation and position sizing."""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import (
    RiskEngineError,
    InsufficientBuyingPowerError,
    MaxDrawdownExceededError,
    SignalScoreTooLowError
)
from app.models.signals import StrategySignal
from app.models.trading import AccountModel, PositionModel

logger = logging.getLogger(__name__)


class RiskDecision(BaseModel):
    """Risk engine decision for a trade."""
    allowed: bool
    max_position_value: Optional[float] = None
    suggested_shares: Optional[int] = None
    reason: Optional[str] = None
    risk_score: float = Field(0.0, ge=0, le=100)
    warnings: List[str] = Field(default_factory=list)


class RiskEngine:
    """Evaluate trades and manage portfolio risk."""

    def __init__(self):
        """Initialize risk engine with configuration."""
        self.settings = get_settings()
        self.max_position_risk = self.settings.TRADING_DEFAULT_MAX_POSITION_RISK
        self.max_daily_drawdown = self.settings.TRADING_DAILY_MAX_DRAWDOWN
        self.min_signal_score = self.settings.TRADING_MIN_SIGNAL_SCORE
        self.urgency_threshold = self.settings.TRADING_FAST_MODE_URGENCY_THRESHOLD

    async def evaluate_risk(
        self,
        signal: StrategySignal,
        account: AccountModel,
        positions: List[PositionModel],
        current_price: float
    ) -> RiskDecision:
        """
        Evaluate if a trade should be allowed based on risk parameters.

        Args:
            signal: AI strategy signal
            account: Current account state
            positions: Open positions
            current_price: Current price of the asset

        Returns:
            RiskDecision with approval and sizing
        """
        decision = RiskDecision(allowed=False, risk_score=0)

        # Check 1: Signal quality
        if signal.final_score < self.min_signal_score:
            decision.reason = f"Signal score {signal.final_score:.1f} below minimum {self.min_signal_score}"
            raise SignalScoreTooLowError(decision.reason)

        # Check 2: Daily drawdown
        daily_pnl = self._calculate_daily_pnl(account, positions)
        if account.portfolio_value > 0 and daily_pnl < -self.max_daily_drawdown * account.portfolio_value:
            decision.reason = f"Daily drawdown {daily_pnl/account.portfolio_value:.2%} exceeds limit {self.max_daily_drawdown:.2%}"
            raise MaxDrawdownExceededError(decision.reason)

        # Check 3: Buying power
        if account.buying_power <= 0:
            decision.reason = "Insufficient buying power"
            raise InsufficientBuyingPowerError(decision.reason)

        # Check 4: Existing position
        existing_position = self._get_position_for_ticker(signal.ticker, positions)
        if existing_position:
            # Allow adding to winners, block adding to losers
            if existing_position.unrealized_plpc < -0.05:  # Down more than 5%
                decision.warnings.append("Existing position is losing, consider closing instead")
                decision.reason = "Existing losing position"
                return decision

        # Check 5: Correlation risk
        correlated_exposure = self._calculate_correlated_exposure(signal.ticker, positions)
        if correlated_exposure > 0.3:  # More than 30% in correlated assets
            decision.warnings.append(f"High correlation exposure: {correlated_exposure:.1%}")

        # Calculate position size
        position_value = self._calculate_position_size(
            signal=signal,
            account=account,
            positions=positions,
            current_price=current_price
        )

        # Final checks
        if position_value < 100:  # Minimum position size
            decision.reason = f"Position size too small: ${position_value:.2f}"
            return decision

        # Calculate risk score (higher is better)
        risk_score = self._calculate_risk_score(
            signal=signal,
            account=account,
            positions=positions,
            position_value=position_value
        )

        # Build successful decision
        decision.allowed = True
        decision.max_position_value = position_value
        decision.suggested_shares = int(position_value / current_price) if current_price > 0 else 0
        decision.risk_score = risk_score
        decision.reason = "Trade approved"

        # Add warnings if needed
        if signal.fast_reaction_mode:
            decision.warnings.append("Fast reaction mode - increased volatility expected")

        if len(positions) > 10:
            decision.warnings.append("Portfolio has many positions - consider consolidation")

        if account.buying_power < account.portfolio_value * 0.1:
            decision.warnings.append("Low buying power remaining")

        logger.info(f"Risk decision for {signal.ticker}: {decision.reason}")
        logger.info(f"Position size: ${position_value:.2f} ({decision.suggested_shares} shares)")

        return decision

    def _calculate_position_size(
        self,
        signal: StrategySignal,
        account: AccountModel,
        positions: List[PositionModel],
        current_price: float
    ) -> float:
        """
        Calculate appropriate position size based on signal and account.

        Args:
            signal: Strategy signal
            account: Account details
            positions: Current positions
            current_price: Asset price

        Returns:
            Position value in dollars
        """
        # Base position size (Kelly Criterion simplified)
        base_size = account.buying_power * self.max_position_risk

        # Adjust for signal strength
        signal_multiplier = signal.final_score / 100.0  # 0 to 1
        confidence_multiplier = signal.news.confidence

        # Adjust for urgency and time horizon
        if signal.fast_reaction_mode and signal.news.urgency > self.urgency_threshold:
            urgency_multiplier = 0.7  # Reduce size for fast trades
        else:
            urgency_multiplier = 1.0

        # Adjust for time horizon
        horizon_multipliers = {
            "scalp": 0.5,
            "swing": 1.0,
            "position": 1.5
        }
        horizon_multiplier = horizon_multipliers.get(signal.time_horizon, 1.0)

        # Adjust for portfolio concentration (tighter sizing as book grows)
        num_positions = len(positions)
        if num_positions > 10:
            concentration_multiplier = 0.6
        elif num_positions > 5:
            concentration_multiplier = 0.8
        else:
            concentration_multiplier = 1.0

        # Calculate final position size
        position_value = (
            base_size *
            signal_multiplier *
            confidence_multiplier *
            urgency_multiplier *
            horizon_multiplier *
            concentration_multiplier
        )

        # Apply caps
        max_allowed = min(
            account.buying_power * 0.5,  # Max 50% of buying power
            account.portfolio_value * 0.1  # Max 10% of portfolio
        )

        position_value = min(position_value, max_allowed)

        # Ensure we can buy at least 1 share
        if current_price > 0 and position_value < current_price:
            position_value = current_price * 1.1  # Add 10% buffer

        return position_value

    def _calculate_risk_score(
        self,
        signal: StrategySignal,
        account: AccountModel,
        positions: List[PositionModel],
        position_value: float
    ) -> float:
        """
        Calculate overall risk score (0-100, higher is better).

        Args:
            signal: Strategy signal
            account: Account details
            positions: Current positions
            position_value: Proposed position value

        Returns:
            Risk score from 0-100
        """
        score = 50.0  # Base score

        # Signal quality factor (+/- 20 points)
        score += (signal.final_score - 50) * 0.4

        # Account health factor (+/- 15 points)
        buying_power_ratio = account.buying_power / account.portfolio_value if account.portfolio_value > 0 else 0
        if buying_power_ratio > 0.5:
            score += 15
        elif buying_power_ratio > 0.2:
            score += 5
        else:
            score -= 10

        # Position sizing factor (+/- 10 points)
        position_ratio = position_value / account.portfolio_value if account.portfolio_value > 0 else 0
        if position_ratio < 0.05:
            score += 10
        elif position_ratio < 0.1:
            score += 5
        else:
            score -= 5

        # Portfolio diversification factor (+/- 10 points)
        if len(positions) < 3:
            score += 10
        elif len(positions) < 7:
            score += 5
        elif len(positions) > 15:
            score -= 10

        # Risk management factor (+/- 10 points)
        if signal.stop_loss_pct < 0.02:
            score += 10
        elif signal.stop_loss_pct < 0.05:
            score += 5
        else:
            score -= 5

        # Cap score between 0 and 100
        return max(0, min(100, score))

    def _calculate_daily_pnl(
        self,
        account: AccountModel,
        positions: List[PositionModel]
    ) -> float:
        """
        Calculate today's P&L.

        Args:
            account: Account details
            positions: Current positions

        Returns:
            Daily P&L in dollars
        """
        # Compare current equity to last equity (from previous close)
        return account.equity - account.last_equity

    def _get_position_for_ticker(
        self,
        ticker: str,
        positions: List[PositionModel]
    ) -> Optional[PositionModel]:
        """
        Find existing position for a ticker.

        Args:
            ticker: Stock symbol
            positions: List of positions

        Returns:
            Position if exists, None otherwise
        """
        for position in positions:
            if position.symbol == ticker:
                return position
        return None

    def _calculate_correlated_exposure(
        self,
        ticker: str,
        positions: List[PositionModel]
    ) -> float:
        """
        Calculate exposure to correlated assets.

        Args:
            ticker: Stock symbol
            positions: Current positions

        Returns:
            Percentage of portfolio in correlated assets
        """
        # Simplified correlation groups
        tech_stocks = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
        financials = ["JPM", "BAC", "WFC", "GS", "MS", "C"]
        energy = ["XOM", "CVX", "COP", "SLB", "EOG"]

        # Determine ticker's group
        ticker_group = None
        if ticker in tech_stocks:
            ticker_group = tech_stocks
        elif ticker in financials:
            ticker_group = financials
        elif ticker in energy:
            ticker_group = energy

        if not ticker_group:
            return 0.0

        # Calculate exposure to same group
        correlated_value = 0.0
        total_value = 0.0

        for position in positions:
            total_value += abs(position.market_value)
            if position.symbol in ticker_group:
                correlated_value += abs(position.market_value)

        if total_value == 0:
            return 0.0

        return correlated_value / total_value