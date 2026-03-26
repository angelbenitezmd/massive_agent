from app.main import app


def test_router_split_preserves_core_paths():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}

    expected = [
        ("/", ("GET",)),
        ("/health", ("GET",)),
        ("/status", ("GET",)),
        ("/api/contract", ("GET",)),
        ("/api/trading/execute", ("POST",)),
        ("/api/trading/manual", ("POST",)),
        ("/api/trading/decision-metrics", ("GET",)),
        ("/api/auto-trade/status", ("GET",)),
        ("/api/auto-trade/enable", ("POST",)),
        ("/api/auto-trade/disable", ("POST",)),
        ("/api/sentiment/{ticker}", ("GET",)),
        ("/api/trading/best-signal", ("GET",)),
        ("/api/trading/all-decisions", ("GET",)),
        ("/api/momentum/{ticker}", ("GET",)),
        ("/api/momentum/scan", ("GET",)),
        ("/api/watchlist", ("GET",)),
        ("/api/scan/watchlist", ("GET",)),
        ("/api/scan/universe", ("GET",)),
        ("/api/scan/spicy", ("GET",)),
        ("/api/trading/positions", ("GET",)),
        ("/api/trading/close/{ticker}", ("POST",)),
        ("/api/trading/reduce/{ticker}", ("POST",)),
        ("/api/trading/close-all", ("POST",)),
        ("/api/trading/check-exits", ("POST",)),
        ("/api/trading/exit-config", ("GET",)),
        ("/api/trading/exit-config", ("PUT",)),
        ("/api/trading/account", ("GET",)),
        ("/api/trading/orders", ("GET",)),
        ("/api/trading/orders", ("DELETE",)),
        ("/api/trading/orders/{order_id}", ("DELETE",)),
        ("/api/portfolio/history", ("GET",)),
        ("/api/trading/closed-trades", ("GET",)),
        ("/api/trading/activity-log", ("GET",)),
        ("/api/trading/monitor-positions", ("POST",)),
        ("/api/trading/position-momentum/{ticker}", ("GET",)),
        ("/api/position-manager/status", ("GET",)),
        ("/api/position-manager/register", ("POST",)),
        ("/api/position-manager/analyze/{symbol}", ("GET",)),
        ("/api/debate/{ticker}", ("GET",)),
        ("/api/memory/similar-trades/{ticker}", ("GET",)),
        ("/api/memory/stats", ("GET",)),
        ("/api/agents/performance", ("GET",)),
        ("/api/agents/weights", ("GET",)),
        ("/api/context/{ticker}", ("GET",)),
    ]

    for path, methods in expected:
        assert any(rp == path and all(m in rm for m in methods) for rp, rm in routes), f"missing route: {path}"

