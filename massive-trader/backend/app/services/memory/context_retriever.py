"""
Context Retriever - Retrieves Historical Context for Decisions.

Provides agents with:
1. Similar past trades and their outcomes
2. Agent accuracy in similar conditions
3. Common pitfalls in this situation
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from app.services.memory.memory_store import MemoryStore, TradeMemory

logger = logging.getLogger(__name__)


@dataclass
class DecisionContext:
    """Context from historical trades for decision-making."""
    similar_trades: List[TradeMemory]
    similar_situation_win_rate: float  # Win rate in similar situations
    agent_accuracy_in_regime: Dict[str, Dict]  # agent -> {accuracy, sample_count}
    common_mistakes: List[TradeMemory]  # High confidence losses
    sample_size: int
    insights: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "similar_trades": [t.to_dict() for t in self.similar_trades],
            "similar_situation_win_rate": self.similar_situation_win_rate,
            "agent_accuracy_in_regime": self.agent_accuracy_in_regime,
            "common_mistakes": [m.to_dict() for m in self.common_mistakes],
            "sample_size": self.sample_size,
            "insights": self.insights,
        }


class ContextRetriever:
    """
    Retrieves relevant past decisions for agent context.

    Provides agents with:
    1. Similar past trades and their outcomes
    2. Agent accuracy in similar conditions
    3. Common pitfalls in this situation
    """

    def __init__(self, memory_store: MemoryStore):
        self.memory = memory_store

    async def get_decision_context(
        self,
        ticker: str,
        market_regime: str,
        technical_regime: str,
        news_sentiment: str,
    ) -> DecisionContext:
        """
        Retrieve relevant historical context for a trading decision.

        Args:
            ticker: Stock ticker
            market_regime: Current market regime (bull/bear/sideways)
            technical_regime: Technical trend regime
            news_sentiment: Current news sentiment

        Returns:
            DecisionContext with historical data
        """
        try:
            # Get similar trades
            similar_trades = await self.memory.get_similar_situations(
                ticker=ticker,
                market_regime=market_regime,
                technical_regime=technical_regime,
                limit=10
            )

            # Calculate win rate for similar situations
            completed = [t for t in similar_trades if t.pnl is not None]
            wins = sum(1 for t in completed if t.pnl and t.pnl > 0)
            total = len(completed)
            similar_win_rate = wins / total if total > 0 else 0.5

            # Get agent accuracy for this regime
            agent_accuracy = {}
            for agent_name in ["news", "technical", "macro", "contrarian", "risk", "timing"]:
                acc = await self.memory.get_agent_accuracy(
                    agent_name, market_regime=market_regime
                )
                agent_accuracy[agent_name] = acc

            # Find common mistakes (high confidence losses)
            mistakes = [
                t for t in similar_trades
                if t.consensus_confidence and t.consensus_confidence > 70
                and t.pnl_percent and t.pnl_percent < -2  # Lost >2%
            ]

            # Generate insights
            insights = self._generate_insights(
                similar_trades, similar_win_rate, agent_accuracy, mistakes
            )

            return DecisionContext(
                similar_trades=similar_trades[:5],  # Top 5 most similar
                similar_situation_win_rate=similar_win_rate,
                agent_accuracy_in_regime=agent_accuracy,
                common_mistakes=mistakes[:3],
                sample_size=total,
                insights=insights,
            )

        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
            return DecisionContext(
                similar_trades=[],
                similar_situation_win_rate=0.5,
                agent_accuracy_in_regime={},
                common_mistakes=[],
                sample_size=0,
                insights=["Error retrieving historical context"],
            )

    def _generate_insights(
        self,
        similar_trades: List[TradeMemory],
        win_rate: float,
        agent_accuracy: Dict[str, Dict],
        mistakes: List[TradeMemory],
    ) -> List[str]:
        """Generate human-readable insights from historical data."""
        insights = []

        # Win rate insight
        if len(similar_trades) >= 5:
            if win_rate > 0.6:
                insights.append(f"Similar situations have {win_rate:.0%} win rate (favorable)")
            elif win_rate < 0.4:
                insights.append(f"Similar situations have {win_rate:.0%} win rate (caution)")

        # Agent accuracy insights
        best_agent = None
        best_accuracy = 0
        worst_agent = None
        worst_accuracy = 1

        for agent, data in agent_accuracy.items():
            if data.get("sample_count", 0) < 5:
                continue
            acc = data.get("accuracy", 0.5)
            if acc > best_accuracy:
                best_accuracy = acc
                best_agent = agent
            if acc < worst_accuracy:
                worst_accuracy = acc
                worst_agent = agent

        if best_agent and best_accuracy > 0.6:
            insights.append(f"{best_agent} agent performs well in this regime ({best_accuracy:.0%} accuracy)")

        if worst_agent and worst_accuracy < 0.4:
            insights.append(f"Caution: {worst_agent} agent struggles in this regime ({worst_accuracy:.0%} accuracy)")

        # Mistake patterns
        if len(mistakes) >= 2:
            insights.append(f"Warning: {len(mistakes)} high-confidence losses in similar situations")

        return insights

    def format_for_prompt(self, context: DecisionContext) -> str:
        """
        Format context for inclusion in agent prompts.

        Returns a string that can be appended to LLM prompts
        to give agents historical context.
        """
        if context.sample_size < 5:
            return "Insufficient historical data for this situation."

        prompt = f"""
HISTORICAL CONTEXT:
- Similar situations win rate: {context.similar_situation_win_rate:.1%} (n={context.sample_size})
"""

        if context.similar_trades:
            prompt += "\nRecent similar trades:\n"
            for trade in context.similar_trades[:3]:
                outcome = "WIN" if trade.pnl and trade.pnl > 0 else "LOSS"
                pnl_str = f"{trade.pnl_percent:+.1f}%" if trade.pnl_percent else "pending"
                prompt += f"- {trade.ticker}: {trade.action_taken} -> {outcome} ({pnl_str})\n"

        if context.common_mistakes:
            prompt += "\nWARNING - Common mistakes in similar situations:\n"
            for mistake in context.common_mistakes:
                prompt += (
                    f"- {mistake.ticker}: High confidence {mistake.consensus_confidence:.0f}%, "
                    f"lost {mistake.pnl_percent:.1f}%\n"
                )

        if context.insights:
            prompt += "\nInsights:\n"
            for insight in context.insights:
                prompt += f"- {insight}\n"

        return prompt

    async def get_ticker_history(
        self,
        ticker: str,
        limit: int = 20,
    ) -> List[TradeMemory]:
        """Get all past trades for a specific ticker."""
        similar = await self.memory.get_similar_situations(
            ticker=ticker,
            market_regime="any",
            technical_regime="any",
            limit=limit,
        )
        # Filter to only this ticker
        return [t for t in similar if t.ticker == ticker]

    async def get_regime_performance(
        self,
        regime: str,
    ) -> Dict[str, Any]:
        """Get overall performance statistics for a market regime."""
        agents = ["news", "technical", "macro", "contrarian", "risk", "timing"]
        performance = {}

        for agent in agents:
            acc = await self.memory.get_agent_accuracy(agent, market_regime=regime)
            performance[agent] = acc

        # Calculate overall regime stats
        all_accuracies = [
            p.get("accuracy", 0.5)
            for p in performance.values()
            if p.get("sample_count", 0) > 0
        ]
        avg_accuracy = sum(all_accuracies) / len(all_accuracies) if all_accuracies else 0.5

        return {
            "regime": regime,
            "agent_performance": performance,
            "avg_accuracy": avg_accuracy,
        }
