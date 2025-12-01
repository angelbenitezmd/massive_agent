"""Dashboard API endpoint for consolidated ticker data."""
import logging
from fastapi import APIRouter, HTTPException

from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/{ticker}")
async def get_dashboard(ticker: str):
    """Return aggregated data for the Streamlit dashboard."""
    service = DashboardService()
    try:
        return await service.get_dashboard_state(ticker)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to build dashboard payload for {ticker}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build dashboard payload") from exc

