"""Pydantic models for Benzinga earnings data."""
from datetime import datetime, date
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field


class EarningsItem(BaseModel):
    """Earnings announcement details."""
    actual_eps: Optional[float] = None
    actual_revenue: Optional[float] = None
    benzinga_id: str
    company_name: str
    currency: Optional[str] = None
    date: date
    date_status: Optional[Literal["projected", "confirmed"]] = None
    eps_method: Optional[Literal["gaap", "ffo", "adj"]] = None
    eps_surprise: Optional[float] = None
    eps_surprise_percent: Optional[float] = None
    estimated_eps: Optional[float] = None
    estimated_revenue: Optional[float] = None
    fiscal_period: Optional[str] = None  # Q1, Q2, H1, FY, etc.
    fiscal_year: Optional[int] = None
    importance: Optional[int] = Field(None, ge=0, le=5)
    last_updated: datetime
    notes: Optional[str] = None
    previous_eps: Optional[float] = None
    previous_revenue: Optional[float] = None
    revenue_method: Optional[Literal["gaap", "adj", "rental"]] = None
    revenue_surprise: Optional[float] = None
    revenue_surprise_percent: Optional[float] = None
    ticker: str
    time: Optional[str] = None  # HH:MM:SS format


class EarningsResponse(BaseModel):
    """Response from Benzinga earnings endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[EarningsItem]
    status: str