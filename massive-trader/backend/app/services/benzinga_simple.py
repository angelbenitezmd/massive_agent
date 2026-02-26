"""Simplified Benzinga client for Massive API integration."""
import httpx
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date

logger = logging.getLogger(__name__)

# Shared client with connection pooling (reused across all requests)
_shared_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

# Semaphore to limit concurrent API requests (prevents pool exhaustion)
_request_semaphore = asyncio.Semaphore(10)


async def _get_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        async with _client_lock:
            if _shared_client is None or _shared_client.is_closed:
                _shared_client = httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                        keepalive_expiry=30,
                    ),
                    timeout=httpx.Timeout(30.0, connect=10.0),
                    http2=False,
                )
    return _shared_client


class BenzingaClient:
    """Simple Benzinga API client via Massive."""

    def __init__(self, base_url: str, api_key: str):
        """Initialize the Benzinga client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _build_params(self, **kwargs) -> Dict[str, str]:
        """Build query parameters, converting underscores to dots."""
        params = {"apiKey": self.api_key}

        for key, value in kwargs.items():
            if value is not None:
                if "_" in key:
                    parts = key.split("_", 1)
                    if len(parts) == 2 and parts[1] in ["gt", "gte", "lt", "lte", "any_of", "all_of"]:
                        key = f"{parts[0]}.{parts[1]}"

                if isinstance(value, list):
                    value = ",".join(str(v) for v in value)
                elif isinstance(value, (date, datetime)):
                    value = value.strftime("%Y-%m-%d")

                params[key] = str(value)
        return params

    async def _request(self, url: str, params: Dict[str, str], label: str = "API") -> Dict[str, Any]:
        """Make a GET request using the shared connection pool with concurrency limiting."""
        async with _request_semaphore:
            client = await _get_client()
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error ({label}): {e.response.status_code}")
                return {"error": f"HTTP {e.response.status_code}", "message": str(e), "results": []}
            except httpx.PoolTimeout:
                logger.warning(f"Pool timeout ({label}) - too many concurrent requests")
                return {"error": "Pool timeout", "results": []}
            except Exception as e:
                logger.error(f"Error ({label}): {type(e).__name__}: {e}")
                return {"error": "API Error", "message": str(e), "results": []}

    async def get_news(
        self,
        tickers: Optional[str] = None,
        channels: Optional[str] = None,
        published_gte: Optional[str] = None,
        limit: int = 100,
        sort: str = "published.desc"
    ) -> Dict[str, Any]:
        """Fetch real-time news from Benzinga via Massive."""
        params = self._build_params(
            tickers=tickers,
            channels=channels,
            limit=limit,
            sort=sort
        )
        url = f"{self.base_url}/benzinga/v2/news"
        return await self._request(url, params, f"news/{tickers or 'all'}")

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
        return await self._request(url, params, f"earnings/{ticker or 'all'}")

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
        return await self._request(url, params, f"ratings/{ticker or 'all'}")

    async def get_consensus(self, ticker: str) -> Dict[str, Any]:
        """Fetch consensus ratings for a ticker via Massive."""
        params = {"apiKey": self.api_key}
        url = f"{self.base_url}/benzinga/v1/consensus-ratings/{ticker}"
        return await self._request(url, params, f"consensus/{ticker}")

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
        return await self._request(url, params, f"guidance/{ticker or 'all'}")
