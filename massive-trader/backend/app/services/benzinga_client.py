"""Benzinga API client for fetching market data."""
import logging
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Union

from app.core.config import get_settings
from app.core.http_client import AsyncHTTPClient
from app.core.errors import BenzingaAPIError
from app.models.news import NewsResponse
from app.models.firms import FirmsResponse
from app.models.earnings import EarningsResponse
from app.models.guidance import GuidanceResponse
from app.models.consensus import ConsensusResponse
from app.models.ratings import RatingsResponse
from app.models.insights import InsightsResponse
from app.models.analysts import AnalystsResponse

logger = logging.getLogger(__name__)


class BenzingaClient:
    """Client for interacting with Benzinga REST API."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize Benzinga client with configuration."""
        settings = get_settings()
        self.base_url = base_url or settings.BENZINGA_BASE_URL
        self.api_key = api_key or settings.BENZINGA_API_KEY

        # Initialize HTTP client
        self.http_client = AsyncHTTPClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.http_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)

    def _build_params(self, **kwargs) -> Dict[str, Any]:
        """Build query parameters, converting underscores to dots and formatting dates."""
        params = {}
        for key, value in kwargs.items():
            if value is not None:
                # Convert snake_case to dot notation for Benzinga API
                # e.g., published_gt -> published.gt
                if "_" in key:
                    parts = key.split("_", 1)
                    if len(parts) == 2 and parts[1] in ["gt", "gte", "lt", "lte", "any_of", "all_of"]:
                        key = f"{parts[0]}.{parts[1]}"

                # Format datetime/date values to YYYY-MM-DD (Benzinga requires date only)
                if isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d")
                elif isinstance(value, date) and not isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d")
                elif isinstance(value, list):
                    value = ",".join(str(v) for v in value)

                params[key] = value
        return params

    async def get_news(
        self,
        tickers: Optional[Union[str, List[str]]] = None,
        channels: Optional[Union[str, List[str]]] = None,
        tags: Optional[Union[str, List[str]]] = None,
        published: Optional[Union[date, datetime, str]] = None,
        published_gt: Optional[Union[date, datetime, str]] = None,
        published_gte: Optional[Union[date, datetime, str]] = None,
        published_lt: Optional[Union[date, datetime, str]] = None,
        published_lte: Optional[Union[date, datetime, str]] = None,
        channels_any_of: Optional[List[str]] = None,
        channels_all_of: Optional[List[str]] = None,
        tags_any_of: Optional[List[str]] = None,
        tags_all_of: Optional[List[str]] = None,
        author: Optional[str] = None,
        limit: int = 100,
        sort: str = "published.desc"
    ) -> NewsResponse:
        """
        Fetch real-time news from Benzinga.

        Args:
            tickers: Filter by ticker symbols
            channels: Filter by channels
            tags: Filter by tags
            published: Filter by publication date
            published_gt/gte/lt/lte: Date range filters
            channels_any_of/all_of: Channel filters
            tags_any_of/all_of: Tag filters
            author: Filter by author
            limit: Maximum results (default 100, max 50000)
            sort: Sort order (default: published.desc)

        Returns:
            NewsResponse with news items
        """
        params = self._build_params(
            tickers=tickers,
            channels=channels,
            tags=tags,
            published=published,
            published_gt=published_gt,
            published_gte=published_gte,
            published_lt=published_lt,
            published_lte=published_lte,
            channels_any_of=channels_any_of,
            channels_all_of=channels_all_of,
            tags_any_of=tags_any_of,
            tags_all_of=tags_all_of,
            author=author,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v2/news", params=params)
            return NewsResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            raise BenzingaAPIError(f"Failed to fetch news: {str(e)}")

    async def get_firms(
        self,
        benzinga_id: Optional[str] = None,
        benzinga_id_any_of: Optional[List[str]] = None,
        limit: int = 100,
        sort: str = "name.asc"
    ) -> FirmsResponse:
        """Fetch firm details from Benzinga."""
        params = self._build_params(
            benzinga_id=benzinga_id,
            benzinga_id_any_of=benzinga_id_any_of,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v1/firms", params=params)
            return FirmsResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching firms: {e}")
            raise BenzingaAPIError(f"Failed to fetch firms: {str(e)}")

    async def get_earnings(
        self,
        date: Optional[Union[date, str]] = None,
        date_gt: Optional[Union[date, str]] = None,
        date_gte: Optional[Union[date, str]] = None,
        date_lt: Optional[Union[date, str]] = None,
        date_lte: Optional[Union[date, str]] = None,
        ticker: Optional[str] = None,
        ticker_any_of: Optional[List[str]] = None,
        importance: Optional[int] = None,
        importance_gte: Optional[int] = None,
        date_status: Optional[str] = None,
        eps_surprise_percent_gte: Optional[float] = None,
        revenue_surprise_percent_gte: Optional[float] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        limit: int = 100,
        sort: str = "last_updated.desc"
    ) -> EarningsResponse:
        """
        Fetch earnings data from Benzinga.

        Args:
            date/date_gt/date_gte/date_lt/date_lte: Date filters
            ticker/ticker_any_of: Ticker filters
            importance/importance_gte: Importance filters (0-5)
            date_status: confirmed or projected
            eps_surprise_percent_gte: Minimum EPS surprise %
            revenue_surprise_percent_gte: Minimum revenue surprise %
            fiscal_year: Filter by fiscal year
            fiscal_period: Filter by period (Q1, Q2, H1, FY, etc.)
            limit: Maximum results
            sort: Sort order

        Returns:
            EarningsResponse with earnings items
        """
        params = self._build_params(
            date=date,
            date_gt=date_gt,
            date_gte=date_gte,
            date_lt=date_lt,
            date_lte=date_lte,
            ticker=ticker,
            ticker_any_of=ticker_any_of,
            importance=importance,
            importance_gte=importance_gte,
            date_status=date_status,
            eps_surprise_percent_gte=eps_surprise_percent_gte,
            revenue_surprise_percent_gte=revenue_surprise_percent_gte,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v1/earnings", params=params)
            return EarningsResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching earnings: {e}")
            raise BenzingaAPIError(f"Failed to fetch earnings: {str(e)}")

    async def get_guidance(
        self,
        date: Optional[Union[date, str]] = None,
        date_gt: Optional[Union[date, str]] = None,
        date_gte: Optional[Union[date, str]] = None,
        date_lt: Optional[Union[date, str]] = None,
        date_lte: Optional[Union[date, str]] = None,
        ticker: Optional[str] = None,
        ticker_any_of: Optional[List[str]] = None,
        positioning: Optional[str] = None,
        importance: Optional[int] = None,
        importance_gte: Optional[int] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        limit: int = 100,
        sort: str = "date.desc"
    ) -> GuidanceResponse:
        """Fetch corporate guidance from Benzinga."""
        params = self._build_params(
            date=date,
            date_gt=date_gt,
            date_gte=date_gte,
            date_lt=date_lt,
            date_lte=date_lte,
            ticker=ticker,
            ticker_any_of=ticker_any_of,
            positioning=positioning,
            importance=importance,
            importance_gte=importance_gte,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v1/guidance", params=params)
            return GuidanceResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching guidance: {e}")
            raise BenzingaAPIError(f"Failed to fetch guidance: {str(e)}")

    async def get_consensus(
        self,
        ticker: str,
        date_gt: Optional[Union[date, str]] = None,
        date_gte: Optional[Union[date, str]] = None,
        date_lt: Optional[Union[date, str]] = None,
        date_lte: Optional[Union[date, str]] = None,
        limit: int = 100
    ) -> ConsensusResponse:
        """
        Fetch consensus ratings for a ticker.

        Args:
            ticker: Stock symbol (required)
            date_gt/date_gte/date_lt/date_lte: Date range filters
            limit: 
            ximum results

        Returns:
            ConsensusResponse with consensus data
        """
        params = self._build_params(
            date_gt=date_gt,
            date_gte=date_gte,
            date_lt=date_lt,
            date_lte=date_lte,
            limit=limit
        )

        try:
            data = await self.http_client.get(f"/benzinga/v1/consensus-ratings/{ticker}", params=params)
            return ConsensusResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching consensus for {ticker}: {e}")
            raise BenzingaAPIError(f"Failed to fetch consensus: {str(e)}")

    async def get_ratings(
        self,
        date: Optional[Union[date, str]] = None,
        date_gt: Optional[Union[date, str]] = None,
        date_gte: Optional[Union[date, str]] = None,
        date_lt: Optional[Union[date, str]] = None,
        date_lte: Optional[Union[date, str]] = None,
        ticker: Optional[str] = None,
        ticker_any_of: Optional[List[str]] = None,
        importance: Optional[int] = None,
        importance_gte: Optional[int] = None,
        rating_action: Optional[str] = None,
        rating_action_any_of: Optional[List[str]] = None,
        price_target_action: Optional[str] = None,
        benzinga_firm_id: Optional[str] = None,
        limit: int = 100,
        sort: str = "last_updated.desc"
    ) -> RatingsResponse:
        """Fetch analyst ratings from Benzinga."""
        params = self._build_params(
            date=date,
            date_gt=date_gt,
            date_gte=date_gte,
            date_lt=date_lt,
            date_lte=date_lte,
            ticker=ticker,
            ticker_any_of=ticker_any_of,
            importance=importance,
            importance_gte=importance_gte,
            rating_action=rating_action,
            rating_action_any_of=rating_action_any_of,
            price_target_action=price_target_action,
            benzinga_firm_id=benzinga_firm_id,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v1/ratings", params=params)
            return RatingsResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching ratings: {e}")
            raise BenzingaAPIError(f"Failed to fetch ratings: {str(e)}")

    async def get_insights(
        self,
        date: Optional[Union[date, str]] = None,
        date_gt: Optional[Union[date, str]] = None,
        date_gte: Optional[Union[date, str]] = None,
        date_lt: Optional[Union[date, str]] = None,
        date_lte: Optional[Union[date, str]] = None,
        ticker: Optional[str] = None,
        ticker_any_of: Optional[List[str]] = None,
        firm: Optional[str] = None,
        rating_action: Optional[str] = None,
        benzinga_firm_id: Optional[str] = None,
        benzinga_rating_id: Optional[str] = None,
        limit: int = 100,
        sort: str = "last_updated.desc"
    ) -> InsightsResponse:
        """Fetch analyst insights from Benzinga."""
        params = self._build_params(
            date=date,
            date_gt=date_gt,
            date_gte=date_gte,
            date_lt=date_lt,
            date_lte=date_lte,
            ticker=ticker,
            ticker_any_of=ticker_any_of,
            firm=firm,
            rating_action=rating_action,
            benzinga_firm_id=benzinga_firm_id,
            benzinga_rating_id=benzinga_rating_id,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v1/analyst-insights", params=params)
            return InsightsResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching insights: {e}")
            raise BenzingaAPIError(f"Failed to fetch insights: {str(e)}")

    async def get_analysts(
        self,
        benzinga_id: Optional[str] = None,
        benzinga_id_any_of: Optional[List[str]] = None,
        benzinga_firm_id: Optional[str] = None,
        firm_name: Optional[str] = None,
        full_name: Optional[str] = None,
        limit: int = 100,
        sort: str = "full_name.asc"
    ) -> AnalystsResponse:
        """Fetch analyst details from Benzinga."""
        params = self._build_params(
            benzinga_id=benzinga_id,
            benzinga_id_any_of=benzinga_id_any_of,
            benzinga_firm_id=benzinga_firm_id,
            firm_name=firm_name,
            full_name=full_name,
            limit=limit,
            sort=sort
        )

        try:
            data = await self.http_client.get("/benzinga/v1/analysts", params=params)
            return AnalystsResponse(**data)
        except Exception as e:
            logger.error(f"Error fetching analysts: {e}")
            raise BenzingaAPIError(f"Failed to fetch analysts: {str(e)}")