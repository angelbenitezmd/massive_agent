"""Pydantic models for Benzinga guidance data."""
from datetime import datetime, date
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field


class GuidanceItem(BaseModel):
    """Corporate guidance details."""
    benzinga_id: str
    company_name: str
    currency: Optional[str] = None
    date: date
    eps_method: Optional[Literal["gaap", "ffo", "adj"]] = None
    estimated_eps_guidance: Optional[float] = None
    estimated_revenue_guidance: Optional[float] = None
    fiscal_period: Optional[str] = None  # Q1, Q2, Q3, Q4
    fiscal_year: Optional[int] = None
    importance: Optional[int] = Field(None, ge=0, le=5)
    last_updated: datetime
    max_eps_guidance: Optional[float] = None
    max_revenue_guidance: Optional[float] = None
    min_eps_guidance: Optional[float] = None
    min_revenue_guidance: Optional[float] = None
    notes: Optional[str] = None
    positioning: Optional[Literal["primary", "secondary"]] = None
    previous_max_eps_guidance: Optional[float] = None
    previous_max_revenue_guidance: Optional[float] = None
    previous_min_eps_guidance: Optional[float] = None
    previous_min_revenue_guidance: Optional[float] = None
    release_type: Optional[Literal["official", "preliminary"]] = None
    revenue_method: Optional[Literal["gaap", "adj"]] = None
    ticker: str
    time: Optional[str] = None  # HH:MM:SS format


class GuidanceResponse(BaseModel):
    """Response from Benzinga guidance endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[GuidanceItem]
    status: str