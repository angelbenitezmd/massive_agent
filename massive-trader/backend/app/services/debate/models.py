"""
Data models for the debate system.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class DebatePhase(Enum):
    """Phases of a debate round."""
    INITIAL_POSITION = "initial_position"  # Agents present their views
    CHALLENGE = "challenge"  # Contrarian challenges consensus
    REBUTTAL = "rebuttal"  # Agents respond to challenges
    FINAL_VOTE = "final_vote"  # Weighted voting for decision


class Direction(Enum):
    """Trading direction."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class AgentPosition:
    """
    An agent's position in the debate.

    Each agent presents:
    - Their recommended direction (BUY/SELL/HOLD)
    - Their confidence level
    - Key arguments supporting their view
    - Risks they've identified
    """
    agent_name: str
    direction: str  # BUY, SELL, HOLD, STRONG_BUY, STRONG_SELL
    confidence: float  # 0-100
    score: float  # 0-100, normalized score
    reasoning: str
    key_arguments: List[str]
    risks_identified: List[str]
    data_cited: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "direction": self.direction,
            "confidence": self.confidence,
            "score": self.score,
            "reasoning": self.reasoning,
            "key_arguments": self.key_arguments,
            "risks_identified": self.risks_identified,
            "data_cited": self.data_cited,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentPosition":
        return cls(
            agent_name=data.get("agent_name", ""),
            direction=data.get("direction", "HOLD"),
            confidence=data.get("confidence", 50),
            score=data.get("score", 50),
            reasoning=data.get("reasoning", ""),
            key_arguments=data.get("key_arguments", []),
            risks_identified=data.get("risks_identified", []),
            data_cited=data.get("data_cited", {}),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
        )


@dataclass
class Challenge:
    """
    A challenge from one agent to another's position.

    The contrarian agent generates challenges to test the strength
    of other agents' arguments.
    """
    challenger: str  # Agent issuing the challenge
    challenged: str  # Agent being challenged
    challenge_type: str  # "logic_flaw", "missing_factor", "overconfidence", "data_validity"
    challenge_text: str
    evidence: Optional[Dict[str, Any]] = None
    severity: str = "medium"  # "low", "medium", "high"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "challenger": self.challenger,
            "challenged": self.challenged,
            "challenge_type": self.challenge_type,
            "challenge_text": self.challenge_text,
            "evidence": self.evidence,
            "severity": self.severity,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Challenge":
        return cls(
            challenger=data.get("challenger", ""),
            challenged=data.get("challenged", ""),
            challenge_type=data.get("challenge_type", "general"),
            challenge_text=data.get("challenge_text", ""),
            evidence=data.get("evidence"),
            severity=data.get("severity", "medium"),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
        )


@dataclass
class Rebuttal:
    """
    An agent's response to a challenge.
    """
    agent_name: str  # Agent providing the rebuttal
    challenge_id: str  # Reference to the challenge
    rebuttal_text: str
    concedes_point: bool = False  # True if agent acknowledges the challenge
    adjusted_confidence: Optional[float] = None  # New confidence if adjusted
    additional_evidence: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "challenge_id": self.challenge_id,
            "rebuttal_text": self.rebuttal_text,
            "concedes_point": self.concedes_point,
            "adjusted_confidence": self.adjusted_confidence,
            "additional_evidence": self.additional_evidence,
            "timestamp": self.timestamp,
        }


@dataclass
class DebateRound:
    """
    A complete debate round with all phases.
    """
    ticker: str
    phase: DebatePhase
    positions: List[AgentPosition]
    challenges: List[Challenge]
    rebuttals: List[Rebuttal]
    start_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "phase": self.phase.value,
            "positions": [p.to_dict() for p in self.positions],
            "challenges": [c.to_dict() for c in self.challenges],
            "rebuttals": [r.to_dict() for r in self.rebuttals],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class DebateOutcome:
    """
    The final outcome of a debate.

    Contains:
    - The final trading decision
    - Vote breakdown by agent
    - Key agreements and disagreements
    - Risk warnings
    - Summary of the debate
    """
    ticker: str
    final_action: str  # BUY, SELL, HOLD, STRONG_BUY, STRONG_SELL
    consensus_confidence: float  # 0-100, how confident is the consensus
    weighted_score: float  # 0-100, weighted by agent performance

    # Voting details
    vote_breakdown: Dict[str, str]  # agent_name -> direction voted
    vote_weights: Dict[str, float]  # agent_name -> weight used
    total_votes: Dict[str, float]  # direction -> total weighted votes

    # Risk management
    risk_veto: bool = False  # True if risk agent vetoed
    risk_veto_reason: Optional[str] = None

    # Position sizing from risk agent
    suggested_shares: int = 0
    max_position_value: float = 0

    # Stop loss and take profit from consensus
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Debate analysis
    key_agreements: List[str] = field(default_factory=list)
    unresolved_disagreements: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)

    # Summary
    debate_summary: str = ""
    reasoning: str = ""

    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    debate_duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "final_action": self.final_action,
            "consensus_confidence": self.consensus_confidence,
            "weighted_score": self.weighted_score,
            "vote_breakdown": self.vote_breakdown,
            "vote_weights": self.vote_weights,
            "total_votes": self.total_votes,
            "risk_veto": self.risk_veto,
            "risk_veto_reason": self.risk_veto_reason,
            "suggested_shares": self.suggested_shares,
            "max_position_value": self.max_position_value,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "key_agreements": self.key_agreements,
            "unresolved_disagreements": self.unresolved_disagreements,
            "risk_warnings": self.risk_warnings,
            "debate_summary": self.debate_summary,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
            "debate_duration_seconds": self.debate_duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateOutcome":
        return cls(
            ticker=data.get("ticker", ""),
            final_action=data.get("final_action", "HOLD"),
            consensus_confidence=data.get("consensus_confidence", 50),
            weighted_score=data.get("weighted_score", 50),
            vote_breakdown=data.get("vote_breakdown", {}),
            vote_weights=data.get("vote_weights", {}),
            total_votes=data.get("total_votes", {}),
            risk_veto=data.get("risk_veto", False),
            risk_veto_reason=data.get("risk_veto_reason"),
            suggested_shares=data.get("suggested_shares", 0),
            max_position_value=data.get("max_position_value", 0),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
            key_agreements=data.get("key_agreements", []),
            unresolved_disagreements=data.get("unresolved_disagreements", []),
            risk_warnings=data.get("risk_warnings", []),
            debate_summary=data.get("debate_summary", ""),
            reasoning=data.get("reasoning", ""),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            debate_duration_seconds=data.get("debate_duration_seconds"),
        )

    def is_actionable(self) -> bool:
        """Check if this outcome suggests taking action (not HOLD)."""
        return self.final_action in ["BUY", "STRONG_BUY", "SELL", "STRONG_SELL"]

    def is_buy(self) -> bool:
        """Check if this is a buy signal."""
        return self.final_action in ["BUY", "STRONG_BUY"]

    def is_sell(self) -> bool:
        """Check if this is a sell signal."""
        return self.final_action in ["SELL", "STRONG_SELL"]
