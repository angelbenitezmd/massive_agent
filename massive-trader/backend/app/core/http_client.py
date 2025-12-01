"""Async HTTP client with retry logic and logging."""
import asyncio
import logging
from typing import Any, Dict, Optional, Union
from urllib.parse import urlencode

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_log,
    after_log,
    retry_if_exception_type
)

logger = logging.getLogger(__name__)


class AsyncHTTPClient:
    """Async HTTP client with automatic retry and logging."""

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        headers: Optional[Dict[str, str]] = None
    ):
        """
        Initialize the HTTP client.

        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            headers: Default headers for all requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)
        self.max_retries = max_retries
        self.default_headers = headers or {}
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.default_headers
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self.default_headers
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        before=before_log(logger, logging.DEBUG),
        after=after_log(logger, logging.DEBUG)
    )
    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def _build_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Convert parameter dict to query string format, handling dotted notation."""
        if not params:
            return {}

        result = {}
        for key, value in params.items():
            if value is not None:
                # Convert underscores to dots for Benzinga API compatibility
                # e.g., published_gt -> published.gt
                api_key = key.replace("_", ".")

                # Handle list values (comma-separated)
                if isinstance(value, list):
                    result[api_key] = ",".join(str(v) for v in value)
                else:
                    result[api_key] = str(value)

        return result

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make GET request.

        Args:
            path: API endpoint path
            params: Query parameters
            headers: Additional headers
            **kwargs: Additional httpx request arguments

        Returns:
            JSON response as dict
        """
        url = f"{self.base_url}/{path.lstrip('/')}" if self.base_url else path

        # Build query parameters
        processed_params = self._build_params(params)

        # Log the request
        logger.debug(f"GET {url} with params: {processed_params}")

        response = await self._make_request(
            "GET",
            url,
            params=processed_params,
            headers=headers,
            **kwargs
        )

        logger.debug(f"Response status: {response.status_code}")
        return response.json()

    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Union[Dict[str, Any], str]:
        """
        Make POST request.

        Args:
            path: API endpoint path
            json: JSON body
            data: Form data
            headers: Additional headers
            **kwargs: Additional httpx request arguments

        Returns:
            Response (JSON dict or text)
        """
        url = f"{self.base_url}/{path.lstrip('/')}" if self.base_url else path

        logger.debug(f"POST {url}")

        response = await self._make_request(
            "POST",
            url,
            json=json,
            data=data,
            headers=headers,
            **kwargs
        )

        # Try to parse as JSON, fallback to text
        try:
            return response.json()
        except:
            return response.text

    async def delete(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Make DELETE request.

        Args:
            path: API endpoint path
            headers: Additional headers
            **kwargs: Additional httpx request arguments

        Returns:
            Response (JSON dict if available)
        """
        url = f"{self.base_url}/{path.lstrip('/')}" if self.base_url else path

        logger.debug(f"DELETE {url}")

        response = await self._make_request(
            "DELETE",
            url,
            headers=headers,
            **kwargs
        )

        # Try to parse as JSON
        try:
            return response.json()
        except:
            return None

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None