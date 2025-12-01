"""Pydantic models for Benzinga news data."""
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """Individual news article from Benzinga."""
    author: Optional[str] = None
    benzinga_id: int
    body: Optional[str] = None
    channels: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    last_updated: datetime
    published: datetime
    tags: List[str] = Field(default_factory=list)
    teaser: Optional[str] = None
    tickers: List[str] = Field(default_factory=list)
    title: str
    url: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NewsResponse(BaseModel):
    """Response from Benzinga news endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[NewsItem]
    status: str