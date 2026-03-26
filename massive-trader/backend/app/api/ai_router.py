"""AI/debate/memory route registration."""
from typing import Callable, Awaitable, Any

from fastapi import APIRouter


def create_ai_router(
    debate_fn: Callable[..., Awaitable[Any]],
    similar_trades_fn: Callable[..., Awaitable[Any]],
    memory_stats_fn: Callable[..., Awaitable[Any]],
    agent_performance_fn: Callable[..., Awaitable[Any]],
    agent_weights_fn: Callable[..., Awaitable[Any]],
    decision_context_fn: Callable[..., Awaitable[Any]],
) -> APIRouter:
    """Create AI router bound to existing handlers."""
    router = APIRouter(tags=["ai"])
    router.add_api_route("/api/debate/{ticker}", debate_fn, methods=["GET"])
    router.add_api_route("/api/memory/similar-trades/{ticker}", similar_trades_fn, methods=["GET"])
    router.add_api_route("/api/memory/stats", memory_stats_fn, methods=["GET"])
    router.add_api_route("/api/agents/performance", agent_performance_fn, methods=["GET"])
    router.add_api_route("/api/agents/weights", agent_weights_fn, methods=["GET"])
    router.add_api_route("/api/context/{ticker}", decision_context_fn, methods=["GET"])
    return router

