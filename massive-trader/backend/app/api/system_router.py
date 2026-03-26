"""System route registration."""
from typing import Callable, Awaitable, Any

from fastapi import APIRouter


def create_system_router(
    root_fn: Callable[[], Awaitable[Any]],
    health_fn: Callable[[], Awaitable[Any]],
    status_fn: Callable[[], Awaitable[Any]],
    contract_fn: Callable[[], Awaitable[Any]],
) -> APIRouter:
    """Create system router bound to existing handlers."""
    router = APIRouter(tags=["system"])
    router.add_api_route("/", root_fn, methods=["GET"])
    router.add_api_route("/health", health_fn, methods=["GET"])
    router.add_api_route("/status", status_fn, methods=["GET"])
    router.add_api_route("/api/contract", contract_fn, methods=["GET"])
    return router

