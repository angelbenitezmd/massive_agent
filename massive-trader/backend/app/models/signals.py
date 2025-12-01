"""Pydantic models for AI signals and agent outputs."""
from datetime import datetime
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class AgentScore(BaseModel):
    """Score and sentiment from an individual AI agent."""
    score: float = Field(..., ge=0, le=100, description="Score from 0-100")
    sentiment: float = Field(..., ge=-1, le=1, description="Sentiment from -1 to +1")
    confidence: float = Field(..., ge=0, le=1, description="Confidence from 0-1")
    urgency: float = Field(..., ge=0, le=1, description="Urgency from 0-1")
    notes: Optional[str] = Field(None, description="Agent's reasoning notes")


class StrategySignal(BaseModel):
    """Complete trading signal from the AI strategist."""
    ticker: str
    action: Literal["BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"]
    final_score: float = Field(..., ge=0, le=100)

    # Individual agent scores
    news: AgentScore
    earnings: AgentScore
    consensus: AgentScore
    guidance: AgentScore
    risk: AgentScore

    # Strategy parameters
    impact_score: float = Field(..., ge=0, le=100)
    time_horizon: Literal["scalp", "swing", "position"]
    fast_reaction_mode: bool = Field(default=False)

    # Risk management
    stop_loss_pct: float = Field(..., ge=0, le=0.5)  # Max 50% stop loss
    take_profit_pct: float = Field(..., ge=0, le=2.0)  # Max 200% profit target

    # Metadata
    reasoning_tree: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MarketEvent(BaseModel):
    """Market event that triggers analysis."""
    event_type: Literal["news", "earnings", "rating", "guidance", "scheduled"]
    ticker: str
    source_id: Optional[str] = None  # Benzinga ID or other identifier
    urgency: float = Field(0.5, ge=0, le=1)
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)