"""Portfolio/position-manager/trade-ops route registration."""
from typing import Callable, Awaitable, Any

from fastapi import APIRouter


def create_portfolio_router(
    positions_fn: Callable[..., Awaitable[Any]],
    close_position_fn: Callable[..., Awaitable[Any]],
    reduce_position_fn: Callable[..., Awaitable[Any]],
    close_all_fn: Callable[..., Awaitable[Any]],
    check_exits_fn: Callable[..., Awaitable[Any]],
    get_exit_config_fn: Callable[..., Awaitable[Any]],
    update_exit_config_fn: Callable[..., Awaitable[Any]],
    account_fn: Callable[..., Awaitable[Any]],
    orders_fn: Callable[..., Awaitable[Any]],
    portfolio_history_fn: Callable[..., Awaitable[Any]],
    closed_trades_fn: Callable[..., Awaitable[Any]],
    cancel_all_orders_fn: Callable[..., Awaitable[Any]],
    cancel_order_fn: Callable[..., Awaitable[Any]],
    activity_log_fn: Callable[..., Awaitable[Any]],
    monitor_positions_fn: Callable[..., Awaitable[Any]],
    position_momentum_fn: Callable[..., Awaitable[Any]],
    pm_status_fn: Callable[..., Awaitable[Any]],
    pm_register_fn: Callable[..., Awaitable[Any]],
    pm_analyze_fn: Callable[..., Awaitable[Any]],
) -> APIRouter:
    """Create portfolio router bound to existing handlers."""
    router = APIRouter(tags=["portfolio"])
    router.add_api_route("/api/trading/positions", positions_fn, methods=["GET"])
    router.add_api_route("/api/trading/close/{ticker}", close_position_fn, methods=["POST"])
    router.add_api_route("/api/trading/reduce/{ticker}", reduce_position_fn, methods=["POST"])
    router.add_api_route("/api/trading/close-all", close_all_fn, methods=["POST"])
    router.add_api_route("/api/trading/check-exits", check_exits_fn, methods=["POST"])
    router.add_api_route("/api/trading/exit-config", get_exit_config_fn, methods=["GET"])
    router.add_api_route("/api/trading/exit-config", update_exit_config_fn, methods=["PUT"])
    router.add_api_route("/api/trading/account", account_fn, methods=["GET"])
    router.add_api_route("/api/trading/orders", orders_fn, methods=["GET"])
    router.add_api_route("/api/portfolio/history", portfolio_history_fn, methods=["GET"])
    router.add_api_route("/api/trading/closed-trades", closed_trades_fn, methods=["GET"])
    router.add_api_route("/api/trading/orders", cancel_all_orders_fn, methods=["DELETE"])
    router.add_api_route("/api/trading/orders/{order_id}", cancel_order_fn, methods=["DELETE"])
    router.add_api_route("/api/trading/activity-log", activity_log_fn, methods=["GET"])
    router.add_api_route("/api/trading/monitor-positions", monitor_positions_fn, methods=["POST"])
    router.add_api_route("/api/trading/position-momentum/{ticker}", position_momentum_fn, methods=["GET"])
    router.add_api_route("/api/position-manager/status", pm_status_fn, methods=["GET"])
    router.add_api_route("/api/position-manager/register", pm_register_fn, methods=["POST"])
    router.add_api_route("/api/position-manager/analyze/{symbol}", pm_analyze_fn, methods=["GET"])
    return router

