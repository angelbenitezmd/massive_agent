from datetime import datetime

from app import main


def test_calculate_position_size_shrinks_with_loss_multiplier(monkeypatch):
    class DummyTrader:
        @staticmethod
        def get_account_status():
            return {
                "equity": 100_000,
                "daytrading_buying_power": 200_000,
            }

    monkeypatch.setattr(main, "alpaca_trader", DummyTrader())

    full_size = main.calculate_position_size(
        price=100.0,
        stop_loss_price=97.5,
        confidence=0.82,
        signal_score=86,
        performance_multiplier=1.0,
    )
    penalized_size = main.calculate_position_size(
        price=100.0,
        stop_loss_price=97.5,
        confidence=0.82,
        signal_score=86,
        performance_multiplier=0.5,
    )

    assert full_size > 0
    assert penalized_size > 0
    assert penalized_size < full_size


def test_live_trade_gate_blocks_after_daily_trade_cap(monkeypatch):
    today = datetime.utcnow().date().isoformat()
    monkeypatch.setattr(
        main,
        "_activity_log",
        [
            {
                "type": "AUTO_TRADE",
                "action": "BUY",
                "timestamp": f"{today}T1{idx}:00:00",
            }
            for idx in range(main.AUTO_TRADE_MAX_NEW_TRADES_PER_DAY)
        ],
    )

    signal = {
        "ticker": "AAPL",
        "action": "BUY",
        "combined_score": 88.0,
        "ai_score": 80.0,
        "momentum_score": 72.0,
        "price_change_pct": 0.9,
        "llm_enhanced": True,
        "entry_price": 100.0,
        "stop_loss": 97.0,
        "source": "watchlist_auto",
    }

    allowed, reason = main._passes_live_auto_trade_gate(signal, set())
    assert allowed is False
    assert reason == f"daily_trade_cap={main.AUTO_TRADE_MAX_NEW_TRADES_PER_DAY}"


def test_live_trade_gate_applies_feedback_penalty_and_resizes(monkeypatch):
    monkeypatch.setattr(main, "_activity_log", [])

    class DummyTrader:
        @staticmethod
        def get_account_status():
            return {
                "equity": 100_000,
                "daytrading_buying_power": 200_000,
            }

    monkeypatch.setattr(main, "alpaca_trader", DummyTrader())
    monkeypatch.setattr(
        main,
        "_get_trade_feedback",
        lambda _signal: {
            "score_penalty": 8.0,
            "size_multiplier": 0.5,
            "veto": False,
            "reasons": ["negative_recent_expectancy"],
        },
    )

    signal = {
        "ticker": "MSFT",
        "action": "BUY",
        "combined_score": 86.0,
        "ai_score": 79.0,
        "momentum_score": 70.0,
        "price_change_pct": 0.8,
        "llm_enhanced": True,
        "entry_price": 100.0,
        "stop_loss": 97.0,
        "source": "watchlist_auto",
        "quantity": 999,
    }

    baseline_qty = main.calculate_position_size(
        price=100.0,
        stop_loss_price=97.0,
        confidence=0.86,
        signal_score=86,
        performance_multiplier=1.0,
    )

    allowed, reason = main._passes_live_auto_trade_gate(signal, set())

    assert allowed is True
    assert reason == "passed"
    assert signal["effective_score"] == 78.0
    assert signal["position_size_multiplier"] == 0.5
    assert 0 < signal["quantity"] < baseline_qty


def test_live_trade_gate_allows_true_early_setup_at_lower_score(monkeypatch):
    monkeypatch.setattr(main, "_activity_log", [])

    class DummyTrader:
        @staticmethod
        def get_account_status():
            return {
                "equity": 100_000,
                "daytrading_buying_power": 200_000,
            }

    monkeypatch.setattr(main, "alpaca_trader", DummyTrader())
    monkeypatch.setattr(
        main,
        "_get_trade_feedback",
        lambda _signal: {
            "score_penalty": 0.0,
            "size_multiplier": 1.0,
            "veto": False,
            "reasons": [],
        },
    )

    signal = {
        "ticker": "AMD",
        "action": "BUY",
        "combined_score": 65.0,
        "ai_score": 74.0,
        "momentum_score": 44.0,
        "price_change_pct": 0.7,
        "llm_enhanced": True,
        "entry_price": 102.0,
        "stop_loss": 98.5,
        "risk_reward_ratio": 1.9,
        "buy_gate": {"passed": True, "reasons": []},
        "entry_timing_state": "early",
        "fresh_catalyst": True,
        "source": "watchlist_auto",
    }

    allowed, reason = main._passes_live_auto_trade_gate(signal, set())

    assert allowed is True
    assert reason == "passed"
    assert signal["effective_score"] == 65.0


def test_live_trade_gate_blocks_trending_when_score_not_elite(monkeypatch):
    monkeypatch.setattr(main, "_activity_log", [])
    monkeypatch.setattr(
        main,
        "_get_trade_feedback",
        lambda _signal: {
            "score_penalty": 0.0,
            "size_multiplier": 1.0,
            "veto": False,
            "reasons": [],
        },
    )

    signal = {
        "ticker": "NVDA",
        "action": "BUY",
        "combined_score": max(
            main.AUTO_TRADE_MIN_COMBINED_SCORE + 1.0,
            main.AUTO_TRADE_TRENDING_MIN_COMBINED_SCORE - 1.0,
        ),
        "ai_score": 78.0,
        "momentum_score": 69.0,
        "price_change_pct": 0.7,
        "llm_enhanced": True,
        "entry_price": 120.0,
        "stop_loss": 116.0,
        "source": "trending",
    }

    allowed, reason = main._passes_live_auto_trade_gate(signal, set())
    assert allowed is False
    assert reason == (
        f"trending_score={signal['combined_score']:.1f}"
        f"<min={main.AUTO_TRADE_TRENDING_MIN_COMBINED_SCORE:.1f}"
    )
