from datetime import datetime
from types import SimpleNamespace

from app.main import _pair_closed_trades_from_orders, _summarize_closed_trades


def _filled_order(*, order_id: str, symbol: str, side: str, qty: float, price: float, filled_at: datetime):
    return SimpleNamespace(
        id=order_id,
        symbol=symbol,
        side=SimpleNamespace(value=side),
        status=SimpleNamespace(value="filled"),
        filled_qty=qty,
        filled_avg_price=price,
        filled_at=filled_at,
    )


def test_pair_closed_trades_preserves_partial_fill_fifo():
    orders = [
        _filled_order(order_id="buy-1", symbol="AAPL", side="buy", qty=10, price=100, filled_at=datetime(2026, 4, 21, 9, 30)),
        _filled_order(order_id="buy-2", symbol="AAPL", side="buy", qty=5, price=102, filled_at=datetime(2026, 4, 21, 9, 45)),
        _filled_order(order_id="sell-1", symbol="AAPL", side="sell", qty=8, price=105, filled_at=datetime(2026, 4, 21, 10, 0)),
        _filled_order(order_id="sell-2", symbol="AAPL", side="sell", qty=7, price=101, filled_at=datetime(2026, 4, 21, 10, 30)),
    ]

    trades = _pair_closed_trades_from_orders(orders)

    assert len(trades) == 3
    assert trades[0]["timestamp"] == datetime(2026, 4, 21, 10, 30).isoformat()
    assert trades[0]["quantity"] == 5
    assert trades[0]["pnl_dollars"] == -5.0
    assert trades[1]["quantity"] == 2
    assert trades[1]["pnl_dollars"] == 2.0
    assert trades[2]["quantity"] == 8
    assert trades[2]["pnl_dollars"] == 40.0


def test_summarize_closed_trades_uses_weighted_capital_not_sum_of_percents():
    trades = [
        {
            "id": "t1",
            "symbol": "AAPL",
            "timestamp": datetime(2026, 4, 21, 10, 0).isoformat(),
            "entry_price": 100.0,
            "exit_price": 105.0,
            "quantity": 8,
            "pnl_pct": 5.0,
            "pnl_dollars": 40.0,
            "entry_notional": 800.0,
        },
        {
            "id": "t2",
            "symbol": "AAPL",
            "timestamp": datetime(2026, 4, 21, 10, 30).isoformat(),
            "entry_price": 100.0,
            "exit_price": 101.0,
            "quantity": 2,
            "pnl_pct": 1.0,
            "pnl_dollars": 2.0,
            "entry_notional": 200.0,
        },
        {
            "id": "t3",
            "symbol": "AAPL",
            "timestamp": datetime(2026, 4, 21, 10, 30).isoformat(),
            "entry_price": 102.0,
            "exit_price": 101.0,
            "quantity": 5,
            "pnl_pct": -0.98,
            "pnl_dollars": -5.0,
            "entry_notional": 510.0,
        },
    ]

    summary = _summarize_closed_trades(trades)

    assert summary["total_trades"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["win_rate"] == 66.7
    assert summary["total_pnl_dollars"] == 37.0
    assert summary["total_pnl_pct"] == 2.45
    assert summary["profit_factor"] == 8.4
    assert summary["payoff_ratio"] == 4.2
