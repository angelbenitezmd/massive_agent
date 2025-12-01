"""Pydantic models for Benzinga analyst ratings data."""
from datetime import datetime, date
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field


class RatingItem(BaseModel):
    """Individual analyst rating."""
    adjusted_price_target: Optional[float] = None
    analyst: Optional[str] = None
    benzinga_analyst_id: Optional[str] = None
    benzinga_calendar_url: Optional[str] = None
    benzinga_firm_id: Optional[str] = None
    benzinga_id: str
    benzinga_news_url: Optional[str] = None
    company_name: str
    currency: Optional[str] = None
    date: date
    firm: str
    importance: Optional[int] = Field(None, ge=0, le=5)
    last_updated: datetime
    notes: Optional[str] = None
    previous_adjusted_price_target: Optional[float] = None
    previous_price_target: Optional[float] = None
    previous_rating: Optional[str] = None
    price_percent_change: Optional[float] = None
    price_target: Optional[float] = None
    price_target_action: Optional[Literal["raises", "lowers", "maintains", "announces", "sets"]] = None
    rating: Optional[str] = None
    rating_action: Optional[Literal[
        "downgrades", "maintains", "reinstates", "reiterates", "upgrades",
        "assumes", "initiates_coverage_on", "terminates_coverage_on",
        "removes", "suspends", "firm_dissolved"
    ]] = None
    ticker: str
    time: Optional[str] = None  # HH:MM:SS format


class RatingsResponse(BaseModel):
    """Response from Benzinga ratings endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[RatingItem]
    status: str