"""Main FastAPI application for AI Trading System."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import dashboard
from app.core.config import get_settings
from app.core.logging_config import setup_logging

# Import routers (to be created)
# from app.api import benzinga_news, benzinga_earnings, ...

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    settings = get_settings()
    setup_logging(
        log_level=settings.LOG_LEVEL,
        log_file=settings.LOG_FILE
    )

    logger.info("Starting AI Trading System")
    logger.info(f"Trading Environment: {settings.ALPACA_ENV.upper()}")

    if settings.ALPACA_ENV == "live":
        logger.warning("⚠️ LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
    else:
        logger.info("✅ Paper trading mode (safe)")

    yield

    # Shutdown
    logger.info("Shutting down AI Trading System")


# Create FastAPI app
app = FastAPI(
    title="AI Trading Intelligence System",
    description="Benzinga data + AI agents + Alpaca trading",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.WS_ALLOWED_ORIGINS.split(",") if settings.WS_ALLOWED_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ALPACA_ENV,
        "paper_trading": settings.is_paper_trading
    }


# System status endpoint
@app.get("/status")
async def system_status():
    """Get system status and configuration."""
    return {
        "trading_env": settings.ALPACA_ENV,
        "is_paper": settings.is_paper_trading,
        "risk_settings": {
            "max_position_risk": settings.TRADING_DEFAULT_MAX_POSITION_RISK,
            "daily_max_drawdown": settings.TRADING_DAILY_MAX_DRAWDOWN,
            "min_signal_score": settings.TRADING_MIN_SIGNAL_SCORE
        },
        "watchlist": settings.watchlist,
        "hybrid_interval": settings.TRADING_HYBRID_INTERVAL_SECONDS
    }


# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")


manager = ConnectionManager()


@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket endpoint for streaming AI signals."""
    await manager.connect(websocket)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "status",
            "data": {"connected": True, "endpoint": "signals"}
        })
        while True:
            try:
                # Use wait_for with timeout to allow heartbeat
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client messages (ping/pong)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send heartbeat on timeout
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    """WebSocket endpoint for streaming trade executions."""
    await manager.connect(websocket)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "status",
            "data": {"connected": True, "endpoint": "trades"}
        })
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint for system status updates."""
    await manager.connect(websocket)
    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "data": {
                "connected": True,
                "endpoint": "status",
                "environment": settings.ALPACA_ENV,
                "paper_trading": settings.is_paper_trading
            }
        })

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Include routers
app.include_router(dashboard.router)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "message": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
