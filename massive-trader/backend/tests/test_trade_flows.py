import asyncio

from app import main
from app.services.trade_policy import should_execute_auto_trade


def test_execute_trade_flow_buy_signal(monkeypatch):
    async def fake_analyze(_ticker: str):
        return {
            "ticker": "AAPL",
            "action": "BUY",
            "combined_score": 84.0,
            "buy_gate": {"passed": True},
            "price": 200.0,
            "quantity": 2,
        }

    monkeypatch.setattr(main, "_analyze_ticker_for_signal", fake_analyze)
    monkeypatch.setattr(main.alpaca_trader, "get_positions", lambda: [])
    monkeypatch.setattr(
        main.alpaca_trader,
        "execute_trade",
        lambda signal: {"status": "executed", "order_id": "ord_1", "quantity": signal.get("quantity", 1)},
    )
    monkeypatch.setattr(main, "log_activity", lambda **_: None)
    main._last_trade_execution = {"time": 0, "ticker": None}

    result = asyncio.run(main.execute_trade(auto=True, ticker="AAPL"))
    assert result["status"] == "executed"
    assert result["execution"]["status"] == "executed"


def test_manual_trade_validation_flow():
    main._last_trade_execution = {"time": 0, "ticker": None}
    bad_request = main.ManualTradeRequest(
        ticker="AAPL",
        side="buy",
        quantity=0,
        order_type="market",
        time_in_force="day",
    )
    result = asyncio.run(main.execute_manual_trade(bad_request))
    assert result["status"] == "error"
    assert "Quantity must be positive" in result["message"]


def test_auto_trade_policy_flow():
    signal = {
        "action": "BUY",
        "combined_score": 82.0,
        "buy_gate": {"passed": True, "reasons": []},
    }
    should_trade, reason = should_execute_auto_trade(signal, min_score=70)
    assert should_trade is True
    assert reason == "passed"

    rejected_signal = {
        "action": "HOLD",
        "combined_score": 82.0,
        "buy_gate": {"passed": False, "reasons": ["insufficient_agent_agreement"]},
    }
    should_trade, reason = should_execute_auto_trade(rejected_signal, min_score=70)
    assert should_trade is False
    assert reason.startswith("action=HOLD")

