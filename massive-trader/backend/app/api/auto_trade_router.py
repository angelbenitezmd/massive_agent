"""Auto-trade route registration."""
from typing import Callable, Awaitable, Any

from fastapi import APIRouter


def create_auto_trade_router(
    status_fn: Callable[..., Awaitable[Any]],
    enable_fn: Callable[..., Awaitable[Any]],
    disable_fn: Callable[..., Awaitable[Any]],
) -> APIRouter:
    """Create auto-trade router bound to existing handlers."""
    router = APIRouter(tags=["auto-trade"])
    router.add_api_route("/api/auto-trade/status", status_fn, methods=["GET"])
    router.add_api_route("/api/auto-trade/enable", enable_fn, methods=["POST"])
    router.add_api_route("/api/auto-trade/disable", disable_fn, methods=["POST"])
    return router

