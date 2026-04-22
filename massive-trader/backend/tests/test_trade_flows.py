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


def test_signal_analysis_builds_trade_plan(monkeypatch):
    async def fake_momentum(_ticker: str):
        return {
            "momentum_score": 72.0,
            "signals": ["Volume expanding", "Trend up"],
        }

    async def fake_sentiment(_ticker: str, use_llm: bool = False):
        if use_llm:
            return {
                "score": 84.0,
                "llm_enhanced": True,
                "summary": "Catalyst confirmed with favorable news flow.",
            }
        return {
            "score": 79.0,
            "shrinkage": {},
        }

    async def fake_quote(_ticker: str):
        return {
            "price": 119.8,
            "change_percent": 0.9,
            "high": 124.0,
            "low": 117.5,
            "prev_close": 118.6,
        }

    async def fake_bars(_ticker: str, timeframe: str = "15Min", limit: int = 80):
        return [
            {
                "open": 119.2,
                "high": 120.3,
                "low": 118.9,
                "close": 119.8,
                "volume": 140000 if i >= limit - 5 else 100000,
            }
            for i in range(limit)
        ]

    def fake_technical_context(_ticker: str, _price: float, _bars: list):
        return {
            "technical_veto": False,
            "technical_veto_reason": None,
            "technical_score": 69.0,
            "technical_regime": "bullish",
            "technical_rsi": 58.0,
            "technical_bias_points": 1.5,
            "support": 117.0,
            "resistance": 126.0,
            "atr": 1.1,
            "relative_volume": 1.35,
            "resistance_room_pct": 5.18,
            "support_room_pct": 2.34,
        }

    monkeypatch.setattr(main, "get_momentum_analysis", fake_momentum)
    monkeypatch.setattr(main, "get_sentiment", fake_sentiment)
    monkeypatch.setattr(main, "get_quote", fake_quote)
    monkeypatch.setattr(main, "get_bars", fake_bars)
    monkeypatch.setattr(main, "_technical_context_from_bars", fake_technical_context)

    result = asyncio.run(main._analyze_ticker_for_signal("NVDA"))

    assert result["action"] == "BUY"
    assert result["buy_gate"]["passed"] is True
    assert result["risk_reward_ratio"] >= 1.8
    assert result["quantity"] > 0
    assert result["technical_score"] is not None
    assert result["entry_window"] in {"early", "standard", "late", "extended"}
