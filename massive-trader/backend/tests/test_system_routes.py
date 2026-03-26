import pytest
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.main import app, check_trade_allowed, calculate_position_size


def test_check_trade_allowed_requires_llm_confirmation(monkeypatch):
    # Force market-hours and bypass external dependencies
    from app import main as main_mod

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            dt = datetime(2026, 3, 11, 10, 0, 0)  # Wednesday, 10:00 ET
            return dt if tz is None else dt.replace(tzinfo=tz)

    monkeypatch.setattr(main_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(main_mod, "_check_daily_loss_limit", lambda: False)
    monkeypatch.setattr(main_mod, "_check_spy_trend", lambda: (False, 0.0))
    monkeypatch.setattr(main_mod, "alpaca_trader", None)

    res = check_trade_allowed("AAPL", score=90, llm_enhanced=False, source="test")
    assert res["allowed"] is False
    assert "LLM" in res["reason"] or "keyword-only" in res["reason"]


def test_calculate_position_size_basic(monkeypatch):
    from app import main as main_mod

    class DummyTrader:
        @staticmethod
        def get_account_status():
            return {
                "equity": 100_000,
                "daytrading_buying_power": 200_000,
            }

    monkeypatch.setattr(main_mod, "alpaca_trader", DummyTrader())

    shares = calculate_position_size(price=100.0, stop_loss_price=95.0, confidence=0.8, risk_pct=0.02, signal_score=85)
    assert isinstance(shares, int)
    assert shares > 0


@pytest.mark.asyncio
async def test_root_route_basic():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("message") == "AI Trading System API"
    assert "version" in data


@pytest.mark.asyncio
async def test_health_route_basic():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"
    assert "environment" in data
    assert "paper_trading" in data


@pytest.mark.asyncio
async def test_status_route_basic():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "trading_env" in data
    assert "api_keys_configured" in data


def test_execution_status_normalization():
    from app import main as main_mod

    assert main_mod._is_successful_execution_result({"status": "executed"}) is True
    assert main_mod._is_successful_execution_result({"status": "filled"}) is True
    assert main_mod._is_successful_execution_result({"status": "submitted"}) is True
    assert main_mod._is_successful_execution_result({"status": "simulated"}) is True
    assert main_mod._is_successful_execution_result({"status": "error"}) is False
    assert main_mod._is_successful_execution_result({"status": "skipped"}) is False
    assert main_mod._is_successful_execution_result(None) is False


@pytest.mark.asyncio
async def test_execute_trade_does_not_set_cooldown_on_non_success(monkeypatch):
    from app import main as main_mod

    async def fake_analyze(_ticker):
        return {
            "ticker": "AAPL",
            "action": "BUY",
            "combined_score": 90,
            "llm_enhanced": True,
        }

    class DummyTrader:
        @staticmethod
        def get_positions():
            return []

        @staticmethod
        def execute_trade(_signal):
            return {"status": "skipped", "message": "No action needed"}

    monkeypatch.setattr(main_mod, "_analyze_ticker_for_signal", fake_analyze)
    monkeypatch.setattr(main_mod, "check_trade_allowed", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(main_mod, "alpaca_trader", DummyTrader())
    monkeypatch.setattr(main_mod, "_last_trade_execution", {"time": 0, "ticker": None})

    response = await main_mod.execute_trade(auto=True, ticker="AAPL")

    assert response["status"] == "error"
    assert main_mod._last_trade_execution["time"] == 0
    assert main_mod._last_trade_execution["ticker"] is None


@pytest.mark.asyncio
async def test_execute_trade_sets_cooldown_on_success(monkeypatch):
    from app import main as main_mod

    async def fake_analyze(_ticker):
        return {
            "ticker": "AAPL",
            "action": "BUY",
            "combined_score": 90,
            "llm_enhanced": True,
        }

    class DummyTrader:
        @staticmethod
        def get_positions():
            return []

        @staticmethod
        def execute_trade(_signal):
            return {"status": "executed", "order_id": "123"}

    monkeypatch.setattr(main_mod, "_analyze_ticker_for_signal", fake_analyze)
    monkeypatch.setattr(main_mod, "check_trade_allowed", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(main_mod, "alpaca_trader", DummyTrader())
    monkeypatch.setattr(main_mod, "_last_trade_execution", {"time": 0, "ticker": None})

    response = await main_mod.execute_trade(auto=True, ticker="AAPL")

    assert response["status"] == "executed"
    assert main_mod._last_trade_execution["ticker"] == "AAPL"
    assert main_mod._last_trade_execution["time"] > 0

