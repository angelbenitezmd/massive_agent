"""Pydantic models for trading operations."""
from datetime import datetime
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class TradeOrder(BaseModel):
    """Order to be placed with Alpaca."""
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)
    order_type: Literal["market", "limit", "stop", "bracket", "oco"] = "market"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    time_in_force: Literal["day", "gtc", "ioc", "fok"] = "day"
    env: Literal["paper", "live"] = "paper"
    extended_hours: bool = False


class ExecutedTrade(BaseModel):
    """Record of an executed trade."""
    id: str
    order: TradeOrder
    filled_qty: float
    avg_fill_price: float
    status: Literal["pending", "filled", "partial", "cancelled", "rejected"]
    opened_at: datetime
    closed_at: Optional[datetime] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    journal_notes: Optional[str] = None
    ai_signal_snapshot: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AccountModel(BaseModel):
    """Alpaca account information."""
    id: str
    account_number: str
    status: str
    currency: str
    buying_power: float
    cash: float
    portfolio_value: float
    equity: float
    last_equity: float
    long_market_value: float
    short_market_value: float
    initial_margin: float
    maintenance_margin: float
    daytrade_count: int
    pattern_day_trader: bool


class PositionModel(BaseModel):
    """Open position details."""
    asset_id: str
    symbol: str
    exchange: str
    asset_class: str
    qty: float
    avg_entry_price: float
    side: Literal["long", "short"]
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_plpc: float
    current_price: float
    lastday_price: float
    change_today: float


class OrderModel(BaseModel):
    """Alpaca order details."""
    id: str
    client_order_id: str
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime
    filled_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    asset_id: str
    symbol: str
    asset_class: str
    qty: float
    filled_qty: float
    side: Literal["buy", "sell"]
    order_type: str
    time_in_force: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    filled_avg_price: Optional[float] = None
    status: str
    extended_hours: bool
    order_class: str


class QuoteModel(BaseModel):
    """Market quote data."""
    symbol: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    last: float
    timestamp: datetime