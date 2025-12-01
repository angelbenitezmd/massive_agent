"""Pydantic models for Benzinga analyst insights data."""
from datetime import datetime, date
from typing import List, Optional, Union, Literal
from pydantic import BaseModel


class InsightItem(BaseModel):
    """Analyst insight with reasoning."""
    benzinga_firm_id: str
    benzinga_id: str
    benzinga_rating_id: str
    company_name: Optional[str] = None
    date: date
    firm: str
    insight: str  # Narrative commentary
    last_updated: datetime
    price_target: Optional[float] = None
    rating: Optional[str] = None
    rating_action: Optional[Literal[
        "downgrades", "maintains", "reinstates", "reiterates", "upgrades",
        "assumes", "initiates_coverage_on", "terminates_coverage_on",
        "removes", "suspends", "firm_dissolved"
    ]] = None
    ticker: Optional[str] = None


class InsightsResponse(BaseModel):
    """Response from Benzinga analyst insights endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[InsightItem]
    status: str