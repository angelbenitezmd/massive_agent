"""Analysis and scanning route registration."""
from typing import Callable, Awaitable, Any

from fastapi import APIRouter


def create_analysis_router(
    sentiment_fn: Callable[..., Awaitable[Any]],
    best_signal_fn: Callable[..., Awaitable[Any]],
    all_decisions_fn: Callable[..., Awaitable[Any]],
    momentum_fn: Callable[..., Awaitable[Any]],
    momentum_scan_fn: Callable[..., Awaitable[Any]],
    watchlist_fn: Callable[..., Awaitable[Any]],
    scan_watchlist_fn: Callable[..., Awaitable[Any]],
) -> APIRouter:
    """Create analysis/scanner router bound to existing handlers."""
    router = APIRouter(tags=["analysis"])
    router.add_api_route("/api/sentiment/{ticker}", sentiment_fn, methods=["GET"])
    router.add_api_route("/api/trading/best-signal", best_signal_fn, methods=["GET"])
    router.add_api_route("/api/trading/all-decisions", all_decisions_fn, methods=["GET"])
    router.add_api_route("/api/momentum/{ticker}", momentum_fn, methods=["GET"])
    router.add_api_route("/api/momentum/scan", momentum_scan_fn, methods=["GET"])
    router.add_api_route("/api/watchlist", watchlist_fn, methods=["GET"])
    router.add_api_route("/api/scan/watchlist", scan_watchlist_fn, methods=["GET"])
    return router
