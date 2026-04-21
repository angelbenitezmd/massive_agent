"""
Specialized Trading Agents.

These agents provide deep analysis from different perspectives:
- MacroAgent: Market regime and macro conditions
- ContrarianAgent: Challenge consensus, identify crowded trades
- RiskManagementAgent: Portfolio-level risk analysis
- ExitStrategyAgent: Optimal exit timing
- TradeTimingAgent: Entry timing optimization
"""

from app.services.agents.macro_agent import MacroAgent, MacroSignal
from app.services.agents.contrarian_agent import ContrarianAgent, ContrarianSignal
from app.services.agents.risk_management_agent import RiskManagementAgent, RiskAssessment
from app.services.agents.exit_strategy_agent import ExitStrategyAgent, ExitPlan
from app.services.agents.trade_timing_agent import TradeTimingAgent, TimingRecommendation
from app.services.agents.loss_review_agent import LossReviewAgent, LossReview

__all__ = [
    "MacroAgent",
    "MacroSignal",
    "ContrarianAgent",
    "ContrarianSignal",
    "RiskManagementAgent",
    "RiskAssessment",
    "ExitStrategyAgent",
    "ExitPlan",
    "TradeTimingAgent",
    "TimingRecommendation",
    "LossReviewAgent",
    "LossReview",
]
