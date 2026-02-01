"""
Debate System for Multi-Agent Trading Decisions.

This module implements a crew/debate pattern where multiple agents:
1. Present their initial positions
2. Challenge each other's reasoning
3. Provide rebuttals
4. Vote on the final decision

The system supports:
- Weighted voting based on agent accuracy
- Risk agent veto power
- Consensus thresholds
- Challenge/rebuttal cycles
"""

from app.services.debate.models import (
    DebatePhase,
    AgentPosition,
    Challenge,
    Rebuttal,
    DebateRound,
    DebateOutcome,
)
from app.services.debate.debate_engine import DebateEngine
from app.services.debate.facilitator import DebateFacilitator

__all__ = [
    "DebatePhase",
    "AgentPosition",
    "Challenge",
    "Rebuttal",
    "DebateRound",
    "DebateOutcome",
    "DebateEngine",
    "DebateFacilitator",
]
