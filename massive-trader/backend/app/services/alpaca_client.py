"""Alpaca trading client for order execution and account management."""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.core.config import get_settings
from app.core.http_client import AsyncHTTPClient
from app.core.errors import AlpacaAPIError
from app.models.trading import (
    TradeOrder, AccountModel, PositionModel,
    OrderModel, QuoteModel
)

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Client for interacting with Alpaca trading API."""

    def __init__(self):
        """Initialize Alpaca client with configuration."""
        settings = get_settings()

        # CRITICAL: Check trading environment
        self.is_paper = settings.is_paper_trading
        self.base_url = settings.alpaca_base_url
        self.data_url = settings.ALPACA_DATA_BASE_URL

        # Log trading mode prominently
        if self.is_paper:
            logger.info("="*60)
            logger.info("✅ ALPACA PAPER TRADING MODE (SAFE)")
            logger.info("="*60)
        else:
            logger.warning("="*60)
            logger.warning("⚠️  ALPACA LIVE TRADING MODE - REAL MONEY AT RISK!")
            logger.warning("="*60)

        # Initialize HTTP clients
        self.trading_client = AsyncHTTPClient(
            base_url=self.base_url,
            headers={
                "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
                "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
                "Content-Type": "application/json"
            }
        )

        self.data_client = AsyncHTTPClient(
            base_url=self.data_url,
            headers={
                "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
                "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
                "Content-Type": "application/json"
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.trading_client.__aenter__()
        await self.data_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.trading_client.__aexit__(exc_type, exc_val, exc_tb)
        await self.data_client.__aexit__(exc_type, exc_val, exc_tb)

    async def get_account(self) -> AccountModel:
        """
        Get account information.

        Returns:
            AccountModel with account details
        """
        try:
            data = await self.trading_client.get("/v2/account")
            return AccountModel(**data)
        except Exception as e:
            logger.error(f"Error fetching account: {e}")
            raise AlpacaAPIError(f"Failed to fetch account: {str(e)}")

    async def get_positions(self) -> List[PositionModel]:
        """
        Get all open positions.

        Returns:
            List of PositionModel objects
        """
        try:
            data = await self.trading_client.get("/v2/positions")
            return [PositionModel(**pos) for pos in data]
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            raise AlpacaAPIError(f"Failed to fetch positions: {str(e)}")

    async def get_position(self, symbol: str) -> Optional[PositionModel]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            PositionModel or None if no position
        """
        try:
            data = await self.trading_client.get(f"/v2/positions/{symbol}")
            return PositionModel(**data)
        except Exception as e:
            if "404" in str(e):
                return None
            logger.error(f"Error fetching position for {symbol}: {e}")
            raise AlpacaAPIError(f"Failed to fetch position: {str(e)}")

    async def get_open_orders(self) -> List[OrderModel]:
        """
        Get all open orders.

        Returns:
            List of OrderModel objects
        """
        try:
            data = await self.trading_client.get("/v2/orders", params={"status": "open"})
            return [OrderModel(**order) for order in data]
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            raise AlpacaAPIError(f"Failed to fetch orders: {str(e)}")

    async def place_order(self, order: TradeOrder) -> OrderModel:
        """
        Place a new order.

        Args:
            order: TradeOrder with order details

        Returns:
            OrderModel with order confirmation
        """
        # Build order payload
        payload = {
            "symbol": order.ticker,
            "qty": order.quantity,
            "side": order.side,
            "type": order.order_type,
            "time_in_force": order.time_in_force,
            "extended_hours": order.extended_hours
        }

        # Add price fields if applicable
        if order.limit_price and order.order_type in ["limit", "stop_limit"]:
            payload["limit_price"] = order.limit_price

        if order.stop_price and order.order_type in ["stop", "stop_limit"]:
            payload["stop_price"] = order.stop_price

        # Handle bracket orders
        if order.order_type == "bracket":
            payload["type"] = "market"  # Bracket orders use market type
            payload["order_class"] = "bracket"

            if order.take_profit_price:
                payload["take_profit"] = {"limit_price": order.take_profit_price}

            if order.stop_price:
                payload["stop_loss"] = {"stop_price": order.stop_price}

        # Log order details (without sensitive data)
        logger.info(f"Placing {order.side} order for {order.quantity} {order.ticker}")
        logger.info(f"Order type: {order.order_type}, TIF: {order.time_in_force}")
        logger.info(f"Environment: {'PAPER' if self.is_paper else '⚠️ LIVE'}")

        try:
            data = await self.trading_client.post("/v2/orders", json=payload)
            return OrderModel(**data)
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise AlpacaAPIError(f"Failed to place order: {str(e)}")

    async def cancel_order(self, order_id: str) -> None:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel
        """
        try:
            await self.trading_client.delete(f"/v2/orders/{order_id}")
            logger.info(f"Cancelled order {order_id}")
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise AlpacaAPIError(f"Failed to cancel order: {str(e)}")

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        try:
            await self.trading_client.delete("/v2/orders")
            logger.info("Cancelled all open orders")
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            raise AlpacaAPIError(f"Failed to cancel orders: {str(e)}")

    async def get_order(self, order_id: str) -> OrderModel:
        """
        Get order details by ID.

        Args:
            order_id: Order ID

        Returns:
            OrderModel with order details
        """
        try:
            data = await self.trading_client.get(f"/v2/orders/{order_id}")
            return OrderModel(**data)
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            raise AlpacaAPIError(f"Failed to fetch order: {str(e)}")

    async def get_latest_quote(self, ticker: str) -> QuoteModel:
        """
        Get latest quote for a symbol.

        Args:
            ticker: Stock symbol

        Returns:
            QuoteModel with quote data
        """
        try:
            data = await self.data_client.get(f"/stocks/{ticker}/quotes/latest")
            quote = data.get("quote", {})
            return QuoteModel(
                symbol=ticker,
                bid=quote.get("bp", 0),
                ask=quote.get("ap", 0),
                bid_size=quote.get("bs", 0),
                ask_size=quote.get("as", 0),
                last=quote.get("p", 0),
                timestamp=datetime.fromisoformat(quote.get("t", datetime.utcnow().isoformat()))
            )
        except Exception as e:
            logger.error(f"Error fetching quote for {ticker}: {e}")
            raise AlpacaAPIError(f"Failed to fetch quote: {str(e)}")

    async def get_bars(
        self,
        ticker: str,
        timeframe: str = "1Day",
        limit: int = 100,
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical bars for a symbol.

        Args:
            ticker: Stock symbol
            timeframe: Bar timeframe (1Min, 5Min, 15Min, 1Hour, 1Day)
            limit: Number of bars
            start: Start date (ISO format)
            end: End date (ISO format)

        Returns:
            List of bar data
        """
        params = {
            "timeframe": timeframe,
            "limit": limit
        }

        if start:
            params["start"] = start
        if end:
            params["end"] = end

        try:
            data = await self.data_client.get(f"/stocks/{ticker}/bars", params=params)
            return data.get("bars", [])
        except Exception as e:
            logger.error(f"Error fetching bars for {ticker}: {e}")
            raise AlpacaAPIError(f"Failed to fetch bars: {str(e)}")

    async def close_position(self, symbol: str, qty: Optional[float] = None) -> OrderModel:
        """
        Close a position (sell all or partial).

        Args:
            symbol: Stock symbol
            qty: Quantity to sell (None = sell all)

        Returns:
            OrderModel for the closing order
        """
        position = await self.get_position(symbol)
        if not position:
            raise AlpacaAPIError(f"No position found for {symbol}")

        # Determine quantity to sell
        sell_qty = qty if qty else abs(position.qty)

        # Create sell order
        order = TradeOrder(
            ticker=symbol,
            side="sell" if position.side == "long" else "buy",
            quantity=sell_qty,
            order_type="market",
            time_in_force="day",
            env="paper" if self.is_paper else "live"
        )

        return await self.place_order(order)

    async def close_all_positions(self) -> List[OrderModel]:
        """
        Close all open positions.

        Returns:
            List of OrderModel for closing orders
        """
        positions = await self.get_positions()
        orders = []

        for position in positions:
            try:
                order = await self.close_position(position.symbol)
                orders.append(order)
            except Exception as e:
                logger.error(f"Error closing position {position.symbol}: {e}")

        return orders