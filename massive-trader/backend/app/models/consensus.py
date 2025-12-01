"""Pydantic models for Benzinga consensus ratings data."""
from typing import List, Optional, Union, Literal
from pydantic import BaseModel


class ConsensusRatingItem(BaseModel):
    """Consensus rating for a ticker."""
    buy_ratings: int
    consensus_price_target: float
    consensus_rating: Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
    consensus_rating_value: float  # 1-5 scale
    high_price_target: float
    hold_ratings: int
    low_price_target: float
    price_target_contributors: int
    ratings_contributors: int
    sell_ratings: int
    strong_buy_ratings: int
    strong_sell_ratings: int
    ticker: str


class ConsensusResponse(BaseModel):
    """Response from Benzinga consensus ratings endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[ConsensusRatingItem]
    status: str