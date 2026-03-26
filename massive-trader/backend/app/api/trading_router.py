"""Trading route registration."""
from typing import Callable, Awaitable, Any

from fastapi import APIRouter


def create_trading_router(
    execute_trade_fn: Callable[..., Awaitable[Any]],
    manual_trade_fn: Callable[..., Awaitable[Any]],
    decision_metrics_fn: Callable[..., Awaitable[Any]],
) -> APIRouter:
    """Create trading router bound to existing handlers."""
    router = APIRouter(tags=["trading"])
    router.add_api_route("/api/trading/execute", execute_trade_fn, methods=["POST"])
    router.add_api_route("/api/trading/manual", manual_trade_fn, methods=["POST"])
    router.add_api_route("/api/trading/decision-metrics", decision_metrics_fn, methods=["GET"])
    return router

