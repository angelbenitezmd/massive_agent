"""Simplified Benzinga client for Massive API integration."""
import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date

logger = logging.getLogger(__name__)


class BenzingaClient:
    """Simple Benzinga API client via Massive."""

    def __init__(self, base_url: str, api_key: str):
        """Initialize the Benzinga client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _build_params(self, **kwargs) -> Dict[str, str]:
        """Build query parameters, converting underscores to dots."""
        # Always include API key as query parameter for Massive
        params = {"apiKey": self.api_key}

        for key, value in kwargs.items():
            if value is not None:
                # Convert snake_case to dot notation
                # e.g., published_gt -> published.gt
                if "_" in key:
                    parts = key.split("_", 1)
                    if len(parts) == 2 and parts[1] in ["gt", "gte", "lt", "lte", "any_of", "all_of"]:
                        key = f"{parts[0]}.{parts[1]}"

                # Convert lists to comma-separated strings
                if isinstance(value, list):
                    value = ",".join(str(v) for v in value)
                elif isinstance(value, (date, datetime)):
                    value = value.strftime("%Y-%m-%d")

                params[key] = str(value)
        return params

    async def get_news(
        self,
        tickers: Optional[str] = None,
        channels: Optional[str] = None,
        published_gte: Optional[str] = None,
        limit: int = 100,
        sort: str = "published.desc"
    ) -> Dict[str, Any]:
        """
        Fetch real-time news from Benzinga via Massive.

        Args:
            tickers: Comma-separated ticker symbols
            channels: Filter by channels
            published_gte: Get news after this date
            limit: Maximum results
            sort: Sort order

        Returns:
            News response dict
        """
        params = self._build_params(
            tickers=tickers,
            channels=channels,
            published_gte=published_gte,
            limit=limit,
            sort=sort
        )

        url = f"{self.base_url}/benzinga/v2/news"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
                return {
                    "error": f"HTTP {e.response.status_code}",
                    "message": str(e),
                    "results": []
                }
            except Exception as e:
                logger.error(f"Error fetching news: {e}")
                return {
                    "error": "API Error",
                    "message": str(e),
                    "results": []
                }

    async def get_earnings(
        self,
        ticker: Optional[str] = None,
        date_gte: Optional[str] = None,
        date_lte: Optional[str] = None,
        importance_gte: Optional[int] = None,
        limit: int = 100,
        sort: str = "date.desc"
    ) -> Dict[str, Any]:
        """Fetch earnings data via Massive."""
        params = self._build_params(
            ticker=ticker,
            date_gte=date_gte,
            date_lte=date_lte,
            importance_gte=importance_gte,
            limit=limit,
            sort=sort
        )

        url = f"{self.base_url}/benzinga/v1/earnings"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching earnings: {e}")
                return {"error": str(e), "results": []}

    async def get_ratings(
        self,
        ticker: Optional[str] = None,
        date_gte: Optional[str] = None,
        rating_action: Optional[str] = None,
        limit: int = 100,
        sort: str = "date.desc"
    ) -> Dict[str, Any]:
        """Fetch analyst ratings via Massive."""
        params = self._build_params(
            ticker=ticker,
            date_gte=date_gte,
            rating_action=rating_action,
            limit=limit,
            sort=sort
        )

        url = f"{self.base_url}/benzinga/v1/ratings"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching ratings: {e}")
                return {"error": str(e), "results": []}

    async def get_consensus(self, ticker: str) -> Dict[str, Any]:
        """Fetch consensus ratings for a ticker via Massive."""
        params = {"apiKey": self.api_key}
        url = f"{self.base_url}/benzinga/v1/consensus-ratings/{ticker}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching consensus for {ticker}: {e}")
                return {"error": str(e), "results": []}

    async def get_guidance(
        self,
        ticker: Optional[str] = None,
        date_gte: Optional[str] = None,
        limit: int = 100,
        sort: str = "date.desc"
    ) -> Dict[str, Any]:
        """Fetch corporate guidance via Massive."""
        params = self._build_params(
            ticker=ticker,
            date_gte=date_gte,
            limit=limit,
            sort=sort
        )

        url = f"{self.base_url}/benzinga/v1/guidance"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching guidance: {e}")
                return {"error": str(e), "results": []}