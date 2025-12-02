"""Alpaca paper trading integration for production trading."""
import os
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLossRequest,
    TakeProfitRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, OrderClass
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)


class AlpacaTrader:
    """Production-ready Alpaca paper trading client."""

    def __init__(self):
        """Initialize Alpaca client for PAPER trading."""
        self.api_key = os.getenv("ALPACA_API_KEY_ID")
        self.secret_key = os.getenv("ALPACA_API_SECRET_KEY")

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

            # Get account info
            try:
                account = self.client.get_account()
                logger.info(f"Account Balance: ${account.cash}")
                logger.info(f"Buying Power: ${account.buying_power}")
            except Exception as e:
                logger.error(f"Error getting account: {e}")

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

    def execute_trade(self, signal: Dict) -> Dict:
        """Execute a trade based on unified signal."""
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
            entry_price = signal["entry_price"]
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")

            # Determine order side
            if "BUY" in action.upper():
                side = OrderSide.BUY
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

            # Create bracket order with stop loss + take profit
            if side == OrderSide.BUY and stop_loss and take_profit:
                order_request = MarketOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=side,
                    time_in_force=TimeInForce.GTC,
                    order_class=OrderClass.BRACKET,
                    stop_loss=StopLossRequest(stop_price=round(stop_loss, 2)),
                    take_profit=TakeProfitRequest(limit_price=round(take_profit, 2))
                )
            else:
                # Simple market order
                order_request = MarketOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=side,
                    time_in_force=TimeInForce.GTC
                )

            # Submit order
            order = self.client.submit_order(order_data=order_request)

            return {
                "status": "executed",
                "order_id": order.id,
                "ticker": ticker,
                "side": side.value,
                "quantity": quantity,
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
            # Get current position
            positions = self.client.get_all_positions()
            position = next((p for p in positions if p.symbol == ticker), None)

            if not position:
                return {
                    "status": "no_position",
                    "message": f"No position found for {ticker}"
                }

            # Close position with market order
            order_request = MarketOrderRequest(
                symbol=ticker,
                qty=float(position.qty),
                side=OrderSide.SELL if position.side == "long" else OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )

            order = self.client.submit_order(order_data=order_request)

            return {
                "status": "closed",
                "order_id": order.id,
                "ticker": ticker,
                "quantity": float(position.qty),
                "pnl": float(position.unrealized_pl) if position.unrealized_pl else 0,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error closing position: {e}")
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


# Global trader instance
alpaca_trader = AlpacaTrader()