"""
Weight Adjuster - Adjusts Agent Weights Based on Performance.

Key principles:
1. Recent performance matters more (exponential decay)
2. Regime-specific accuracy (some agents better in certain conditions)
3. Calibration matters (overconfident agents get downweighted)
4. Minimum floor weights (no agent goes to zero)
5. Gradual adjustment (avoid overfitting to recent data)
"""

import logging
from typing import Dict, Optional

from app.services.memory.memory_store import MemoryStore

logger = logging.getLogger(__name__)


class WeightAdjuster:
    """
    Adjusts agent weights based on historical performance.

    The adjustments are:
    - Gradual (max 10% change per update)
    - Bounded (min 5%, max 35%)
    - Data-driven (requires minimum sample size)
    - Calibration-aware (penalizes overconfidence)
    """

    # Default weights if no history
    DEFAULT_WEIGHTS = {
        "news": 0.20,
        "technical": 0.20,
        "macro": 0.15,
        "contrarian": 0.10,
        "risk": 0.15,
        "timing": 0.10,
        "exit": 0.10,
    }

    def __init__(
        self,
        memory_store: MemoryStore,
        min_weight: float = 0.05,
        max_weight: float = 0.35,
        adjustment_rate: float = 0.10,
        min_samples: int = 20,
    ):
        """
        Initialize the weight adjuster.

        Args:
            memory_store: MemoryStore instance for performance data
            min_weight: Minimum weight for any agent (default 5%)
            max_weight: Maximum weight for any agent (default 35%)
            adjustment_rate: Maximum adjustment per update (default 10%)
            min_samples: Minimum trades before adjusting (default 20)
        """
        self.memory = memory_store
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.adjustment_rate = adjustment_rate
        self.min_samples = min_samples

    async def get_adjusted_weights(
        self,
        market_regime: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Get agent weights adjusted for performance.

        Optionally adjusts based on current market regime.

        Args:
            market_regime: Current market regime (bull/bear/sideways)

        Returns:
            Dict of agent_name -> weight (sums to 1.0)
        """
        weights = self.DEFAULT_WEIGHTS.copy()

        for agent_name in weights:
            try:
                # Get performance data
                accuracy_data = await self.memory.get_agent_accuracy(
                    agent_name,
                    period="month",
                    market_regime=market_regime,
                )

                sample_count = accuracy_data.get("sample_count", 0)
                if sample_count < self.min_samples:
                    logger.debug(
                        f"{agent_name}: Insufficient data ({sample_count} samples), using default weight"
                    )
                    continue

                accuracy = accuracy_data.get("accuracy", 0.5)
                calibration = accuracy_data.get("calibration_score", 0.5) or 0.5

                # Calculate adjustment factor
                # accuracy > 0.5 increases weight, < 0.5 decreases
                performance_factor = (accuracy - 0.5) * 2  # -1 to +1

                # Penalize poor calibration (overconfidence)
                calibration_factor = calibration  # 0 to 1

                # Combined adjustment
                adjustment = performance_factor * calibration_factor * self.adjustment_rate

                # Apply adjustment
                new_weight = weights[agent_name] * (1 + adjustment)

                # Clamp to bounds
                new_weight = max(self.min_weight, min(self.max_weight, new_weight))
                weights[agent_name] = new_weight

                logger.debug(
                    f"{agent_name}: accuracy={accuracy:.2f}, calibration={calibration:.2f}, "
                    f"adjustment={adjustment:+.3f}, weight={new_weight:.3f}"
                )

            except Exception as e:
                logger.warning(f"Error adjusting weight for {agent_name}: {e}")
                continue

        # Normalize to sum to 1
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    async def calculate_calibration(
        self,
        agent_name: str,
        period: str = "month",
    ) -> float:
        """
        Calculate how well agent confidence matches outcomes.

        Perfect calibration: 70% confident predictions are right 70% of time.

        Args:
            agent_name: Agent to evaluate
            period: Time period

        Returns:
            Calibration score (0-1, higher is better)
        """
        try:
            # Get predictions grouped by confidence bucket
            predictions = await self.memory.get_predictions_by_confidence(
                agent_name, period
            )

            if not predictions:
                return 0.5

            # Compare predicted confidence to actual accuracy per bucket
            errors = []
            for bucket, data in predictions.items():
                total = data.get("total", 0)
                if total < 3:  # Need minimum sample
                    continue

                expected_accuracy = bucket / 100  # e.g., 70% confidence
                actual_accuracy = data.get("correct", 0) / total
                errors.append(abs(expected_accuracy - actual_accuracy))

            if not errors:
                return 0.5

            # Lower error = better calibration = higher score
            avg_error = sum(errors) / len(errors)
            calibration_score = 1 - min(1, avg_error * 2)  # Scale to 0-1

            return calibration_score

        except Exception as e:
            logger.error(f"Error calculating calibration: {e}")
            return 0.5

    async def get_regime_specific_weights(
        self,
        regime: str,
    ) -> Dict[str, float]:
        """
        Get weights optimized for a specific market regime.

        Some agents perform better in certain conditions:
        - Technical may be better in trending markets
        - Contrarian may be better at extremes
        - Macro may be more important in volatile regimes
        """
        weights = await self.get_adjusted_weights(market_regime=regime)

        # Apply regime-specific heuristics as a secondary adjustment
        if regime == "bull":
            # In bull markets, momentum/technical often more useful
            weights["technical"] = weights.get("technical", 0.20) * 1.1
            weights["macro"] = weights.get("macro", 0.15) * 0.9
        elif regime == "bear":
            # In bear markets, risk management more important
            weights["risk"] = weights.get("risk", 0.15) * 1.2
            weights["contrarian"] = weights.get("contrarian", 0.10) * 1.1
        elif regime == "volatile":
            # In volatile markets, reduce position sizing signals
            weights["timing"] = weights.get("timing", 0.10) * 0.8
            weights["risk"] = weights.get("risk", 0.15) * 1.3

        # Renormalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    async def get_weight_history(
        self,
        agent_name: str,
        periods: int = 10,
    ) -> list:
        """
        Get historical weight changes for an agent (for visualization).

        This would require storing weight history over time.
        For now, returns current weight only.
        """
        current_weights = await self.get_adjusted_weights()
        return [current_weights.get(agent_name, 0.1)]
