"""Pydantic models for Benzinga analyst details data."""
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel


class AnalystItem(BaseModel):
    """Individual analyst details and performance metrics."""
    benzinga_firm_id: str
    benzinga_id: str
    firm_name: str
    full_name: str
    last_updated: datetime
    overall_avg_return: Optional[float] = None
    overall_avg_return_percentile: Optional[float] = None
    overall_success_rate: Optional[float] = None
    smart_score: Optional[float] = None
    total_ratings: Optional[int] = None
    total_ratings_percentile: Optional[float] = None


class AnalystsResponse(BaseModel):
    """Response from Benzinga analysts endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[AnalystItem]
    status: str