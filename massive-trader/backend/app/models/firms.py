"""Pydantic models for Benzinga firms data."""
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel


class FirmItem(BaseModel):
    """Research firm or investment bank details."""
    benzinga_id: str
    currency: Optional[str] = None
    last_updated: datetime
    name: str


class FirmsResponse(BaseModel):
    """Response from Benzinga firms endpoint."""
    count: Optional[int] = None
    next_url: Optional[str] = None
    request_id: Union[int, str]
    results: List[FirmItem]
    status: str