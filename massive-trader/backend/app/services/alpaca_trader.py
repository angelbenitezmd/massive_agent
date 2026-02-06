"""Alpaca paper trading integration for production trading."""
import os
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from types import MethodType
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, OrderClass, QueryOrderStatus
from alpaca.data.live import StockDataStream
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)


class AlpacaTrader:
    """Production-ready Alpaca paper trading client."""

    def __init__(self):
        """Initialize Alpaca client for PAPER trading."""
        self.api_key = os.getenv("ALPACA_API_KEY_ID")
        self.secret_key = os.getenv("ALPACA_API_SECRET_KEY")
        self.is_paper = True  # We always default to paper mode for safety
        self.data_client = None

        if not self.api_key or not self.secret_key:
            logger.warning("Alpaca API keys not configured - running in simulation mode")
            self.client = None
            self.data_stream = None
        else:
            # ALWAYS use paper=True for safety
            self.client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=True  # ALWAYS PAPER TRADING
            )
            logger.info("✅ Alpaca PAPER trading client initialized")
            try:
                self.data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
            except Exception as e:  # pragma: no cover - best-effort init
                logger.warning(f"Could not initialize Alpaca data client: {e}")
                self.data_client = None

            # Backward compatibility: allow legacy submit_order(symbol=..., qty=...) calls
            self._attach_submit_order_adapter()

            # Get account info
            try:
                account = self.client.get_account()
                logger.info(f"Account Balance: ${account.cash}")
                logger.info(f"Buying Power: ${account.buying_power}")
            except Exception as e:
                logger.error(f"Error getting account: {e}")

    def _attach_submit_order_adapter(self) -> None:
        """Wrap submit_order to support legacy keyword args (symbol, qty, etc.)."""
        if not self.client:
            return

        original_submit = self.client.submit_order

        def submit_order_compat(client_self, *args: Any, **kwargs: Any):
            # Legacy style calls pass symbol/qty instead of order_data
            if kwargs and "order_data" not in kwargs and "symbol" in kwargs:
                try:
                    order_request = self._build_order_request_from_kwargs(**kwargs)
                    return original_submit(order_data=order_request)
                except Exception as exc:
                    logger.error(f"Failed to adapt legacy order params: {exc}")
                    raise
            return original_submit(*args, **kwargs)

        # Bind the compatibility wrapper to this client instance
        self.client.submit_order = MethodType(submit_order_compat, self.client)

    def _build_order_request_from_kwargs(self, **kwargs: Any):
        """Convert legacy submit_order kwargs to the new OrderRequest object."""
        symbol = kwargs.get("symbol") or kwargs.get("ticker")
        qty = kwargs.get("qty") or kwargs.get("quantity")
        side = kwargs.get("side") or kwargs.get("order_side")
        order_type = kwargs.get("type") or kwargs.get("order_type") or OrderType.MARKET
        tif = kwargs.get("time_in_force") or kwargs.get("tif") or TimeInForce.GTC
        limit_price = kwargs.get("limit_price")
        stop_price = kwargs.get("stop_price") or kwargs.get("stop_loss")
        order_class = kwargs.get("order_class")
        take_profit = kwargs.get("take_profit")

        if isinstance(side, str):
            side = OrderSide(side.lower())
        if isinstance(order_type, str):
            order_type = OrderType(order_type.lower())
        if isinstance(tif, str):
            tif = TimeInForce(tif.lower())

        # Build the appropriate order request type
        if order_type == OrderType.LIMIT and limit_price is not None:
            order_request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=tif,
                limit_price=round(float(limit_price), 2)
            )
        elif order_type == OrderType.STOP and stop_price is not None:
            order_request = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=tif,
                stop_price=round(float(stop_price), 2)
            )
        else:
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=tif
            )

        # Optional bracket handling for legacy callers
        if order_class and str(order_class).lower() == "bracket":
            tp_req = None
            if take_profit:
                if isinstance(take_profit, TakeProfitRequest):
                    tp_req = take_profit
                elif isinstance(take_profit, dict):
                    tp_req = TakeProfitRequest(**take_profit)
                else:
                    tp_req = TakeProfitRequest(limit_price=round(float(take_profit), 2))

            sl_req = None
            if stop_price:
                if isinstance(stop_price, dict):
                    stop_val = stop_price.get("stop_price") or stop_price.get("limit_price") or stop_price.get("price")
                    if stop_val:
                        sl_req = StopLossRequest(stop_price=round(float(stop_val), 2))
                else:
                    sl_req = StopLossRequest(stop_price=round(float(stop_price), 2))

            order_request.order_class = OrderClass.BRACKET
            if tp_req:
                order_request.take_profit = tp_req
            if sl_req:
                order_request.stop_loss = sl_req

        return order_request

    def get_account_status(self) -> Dict:
        """Get current account status."""
        if not self.client:
            return {
                "status": "simulated",
                "cash": 100000,
                "buying_power": 100000,
                "positions": []
            }

        try:
            account = self.client.get_account()
            positions = self.client.get_all_positions()

            return {
                "status": "connected",
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "equity": float(account.equity),
                "positions": [
                    {
                        "symbol": pos.symbol,
                        "qty": float(pos.qty),
                        "side": pos.side,
                        "avg_entry": float(pos.avg_entry_price),
                        "current": float(pos.current_price) if pos.current_price else 0,
                        "pnl": float(pos.unrealized_pl) if pos.unrealized_pl else 0,
                        "pnl_pct": float(pos.unrealized_plpc) if pos.unrealized_plpc else 0
                    }
                    for pos in positions
                ]
            }
        except Exception as e:
            logger.error(f"Error getting account status: {e}")
            return {"status": "error", "message": str(e)}

    def get_quote(self, ticker: str) -> Dict:
        """Fetch the latest quote for a ticker using the data client."""
        if not self.data_client:
            return {"symbol": ticker.upper(), "price": 0, "bid": 0, "ask": 0}

        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quote = self.data_client.get_stock_latest_quote(request)
            if isinstance(quote, dict):
                quote = quote.get(ticker) or next(iter(quote.values()), None)

            bid = float(getattr(quote, "bid_price", 0) or 0)
            ask = float(getattr(quote, "ask_price", 0) or 0)
            price = float(getattr(quote, "last_price", 0) or (ask or bid))

            return {
                "symbol": ticker.upper(),
                "bid": bid,
                "ask": ask,
                "price": price,
                "timestamp": getattr(quote, "timestamp", None)
            }
        except Exception as e:
            logger.error(f"Error fetching quote for {ticker}: {e}")
            return {"symbol": ticker.upper(), "price": 0, "bid": 0, "ask": 0}

    def execute_trade(self, signal: Dict) -> Dict:
        """Execute a trade with simple market order.

        NOTE: We use simple market orders instead of bracket orders because:
        - Bracket orders with take-profit limits can get stuck in 'pending_cancel' state
        - Stuck orders block position closes (shares are held for the pending order)
        - The position_manager handles all exits with market orders for reliable closes
        """
        if not self.client:
            return {
                "status": "simulated",
                "message": "Trade simulated (no Alpaca connection)",
                "signal": signal
            }

        try:
            ticker = signal["ticker"]
            action = signal["action"]
            quantity = signal.get("quantity", 1)  # Default 1 share for testing
            entry_price = signal.get("entry_price") or signal.get("price", 0)
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")

            # Determine order side
            if "BUY" in action.upper():
                side = OrderSide.BUY

                # Calculate stop-loss and take-profit for logging/tracking
                # (Position manager will use these values for exit decisions)
                if not stop_loss and entry_price:
                    stop_loss = entry_price * 0.95  # 5% stop-loss
                if not take_profit and entry_price:
                    take_profit = entry_price * 1.05  # 5% take-profit

            elif "SELL" in action.upper():
                # Check if we have a position to sell
                positions = self.client.get_all_positions()
                has_position = any(p.symbol == ticker for p in positions)

                if has_position:
                    side = OrderSide.SELL
                else:
                    return {
                        "status": "skipped",
                        "message": f"No position to sell for {ticker}"
                    }
            else:
                return {
                    "status": "skipped",
                    "message": f"No action needed: {action}"
                }

            # SIMPLE MARKET ORDER - position_manager handles all exits
            logger.info(f"📈 MARKET ORDER: {ticker} {side.value} qty={quantity} @ ~${entry_price:.2f}")
            logger.info(f"   Exit targets: stop=${stop_loss:.2f if stop_loss else 0} (-5%), take_profit=${take_profit:.2f if take_profit else 0} (+5%)")
            logger.info(f"   Position manager will monitor and execute exits with market orders")

            order_request = MarketOrderRequest(
                symbol=ticker,
                qty=quantity,
                side=side,
                time_in_force=TimeInForce.DAY  # Day order - cleaner than GTC
            )

            # Submit order
            order = self.client.submit_order(order_data=order_request)

            return {
                "status": "executed",
                "order_id": order.id,
                "ticker": ticker,
                "side": side.value,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_loss": round(stop_loss, 2) if stop_loss else None,
                "take_profit": round(take_profit, 2) if take_profit else None,
                "order_type": "MARKET",
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def close_position(self, ticker: str) -> Dict:
        """Close a position (for momentum exit)."""
        if not self.client:
            return {"status": "simulated"}

        try:
            import time

            # FIRST: Cancel any pending orders for this ticker to free up shares
            # Retry a few times since broker can be slow
            for attempt in range(3):
                try:
                    orders = self.client.get_orders(
                        filter=GetOrdersRequest(
                            status=QueryOrderStatus.OPEN,
                            symbols=[ticker]
                        )
                    )
                    if orders:
                        logger.info(f"Cancelling {len(orders)} pending orders for {ticker} (attempt {attempt+1})")
                        for order in orders:
                            try:
                                self.client.cancel_order_by_id(order.id)
                                logger.info(f"Cancelled order {order.id} for {ticker}")
                            except Exception as cancel_err:
                                # Might already be cancelled/filled
                                logger.debug(f"Could not cancel order {order.id}: {cancel_err}")
                        # Give broker time to process cancellations
                        time.sleep(2)
                    else:
                        break  # No orders to cancel
                except Exception as orders_err:
                    logger.warning(f"Error checking orders for {ticker}: {orders_err}")
                    break

            # Get current position
            positions = self.client.get_all_positions()
            position = next((p for p in positions if p.symbol == ticker), None)

            if not position:
                return {
                    "status": "no_position",
                    "message": f"No position found for {ticker}"
                }

            # Get quantity - use abs() because short positions have negative qty
            raw_qty = float(position.qty)
            qty = abs(raw_qty)

            if qty == 0:
                logger.warning(f"Position {ticker} has qty=0, cannot close")
                return {
                    "status": "invalid_qty",
                    "message": f"Position {ticker} has zero quantity"
                }

            # Determine if long or short based on qty sign or side attribute
            # Short positions have negative qty
            is_short = raw_qty < 0

            # Handle side - position.side can be PositionSide enum or string
            side_str = str(position.side).lower()

            if is_short or "short" in side_str:
                # Short position: buy to cover
                order_side = OrderSide.BUY
                position_type = "SHORT"
            else:
                # Long position: sell to close
                order_side = OrderSide.SELL
                position_type = "LONG"

            logger.info(f"Closing {position_type} position: {ticker} qty={qty} (raw={raw_qty}) -> order_side={order_side}")

            # Use Alpaca's direct close_position API which liquidates the position
            # This is more reliable than submitting a market order when there are pending orders
            try:
                # close_position returns the Order object for the liquidation
                close_result = self.client.close_position(ticker)
                logger.info(f"Position closed via API: {ticker} -> {close_result}")
                return {
                    "status": "closed",
                    "order_id": str(close_result.id) if hasattr(close_result, 'id') else None,
                    "ticker": ticker,
                    "quantity": qty,
                    "position_type": position_type,
                    "pnl": float(position.unrealized_pl) if position.unrealized_pl else 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as close_api_err:
                logger.warning(f"Direct close API failed for {ticker}: {close_api_err}, trying market order")
                # Fallback to market order if direct API fails
                order_request = MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.GTC
                )
                order = self.client.submit_order(order_data=order_request)
                logger.info(f"Position close order submitted: {order.id} for {ticker}")

            return {
                "status": "closed",
                "order_id": order.id,
                "ticker": ticker,
                "quantity": qty,
                "position_type": position_type,
                "pnl": float(position.unrealized_pl) if position.unrealized_pl else 0,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error closing position {ticker}: {e}")
            return {"status": "error", "message": str(e)}

    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        if not self.client:
            return []

        try:
            positions = self.client.get_all_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "side": p.side,
                    "entry": float(p.avg_entry_price),
                    "current": float(p.current_price) if p.current_price else 0,
                    "pnl": float(p.unrealized_pl) if p.unrealized_pl else 0,
                    "pnl_pct": float(p.unrealized_plpc) if p.unrealized_plpc else 0
                }
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def reduce_position(self, ticker: str, quantity: int) -> Dict:
        """Reduce a position by selling/buying a specific quantity."""
        if not self.client:
            return {"status": "simulated"}

        try:
            positions = self.client.get_all_positions()
            position = next((p for p in positions if p.symbol == ticker), None)

            if not position:
                return {"status": "no_position", "message": f"No position for {ticker}"}

            raw_qty = float(position.qty)
            is_short = raw_qty < 0

            # Determine order side (opposite of position)
            order_side = OrderSide.BUY if is_short else OrderSide.SELL

            # Don't reduce more than we have
            max_qty = abs(raw_qty)
            reduce_qty = min(quantity, max_qty)

            order_request = MarketOrderRequest(
                symbol=ticker,
                qty=reduce_qty,
                side=order_side,
                time_in_force=TimeInForce.GTC
            )

            order = self.client.submit_order(order_data=order_request)

            return {
                "status": "reduced",
                "order_id": order.id,
                "ticker": ticker,
                "reduced_qty": reduce_qty,
                "remaining_qty": max_qty - reduce_qty,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error reducing position {ticker}: {e}")
            return {"status": "error", "message": str(e)}

    def close_all_positions(self) -> Dict:
        """Emergency: Close ALL positions."""
        if not self.client:
            return {"status": "simulated"}

        try:
            # Check if market is open
            clock = self.client.get_clock()
            market_open = clock.is_open

            # Get current positions before closing
            positions = self.client.get_all_positions()
            position_count = len(positions)

            if position_count == 0:
                return {
                    "status": "no_positions",
                    "message": "No positions to close",
                    "timestamp": datetime.utcnow().isoformat()
                }

            if not market_open:
                # Market is closed - can't execute market orders
                # Cancel any pending orders first
                try:
                    self.client.cancel_orders()
                except Exception:
                    pass

                return {
                    "status": "market_closed",
                    "message": f"Market is CLOSED. Cannot close {position_count} positions until market opens.",
                    "positions_count": position_count,
                    "positions": [p.symbol for p in positions],
                    "market_open": False,
                    "next_open": clock.next_open.isoformat() if clock.next_open else None,
                    "timestamp": datetime.utcnow().isoformat()
                }

            # Market is open - close immediately
            self.client.close_all_positions(cancel_orders=True)
            return {
                "status": "all_closed",
                "message": f"All {position_count} positions closed",
                "positions_closed": position_count,
                "market_open": True,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return {"status": "error", "message": str(e)}


# Global trader instance
alpaca_trader = AlpacaTrader()
