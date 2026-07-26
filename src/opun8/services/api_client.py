"""
API Client
==========

HTTP client wrapper for making authenticated requests to the OPUN8 backend.

This module provides a clean interface for all API calls, automatically
handling authentication headers, error responses, timeouts, and retries.

Why This File Exists:
    - Centralizes all HTTP logic in one place
    - Automatically adds JWT token to every request
    - Consistent error handling across the codebase
    - Reduces code duplication in service files

Usage:
    from opun8.services.api_client import APIClient

    client = APIClient()
    response = client.get("/user/profile")
    response = client.post("/auth/login", data={"email": "...", "password": "..."})

Author: OPUN8 Team
Version: 1.0.0
"""

import json
from typing import Optional, Dict, Any
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from opun8.services.token_manager import load_token, delete_token


# =============================================================================
# EXCEPTIONS
# =============================================================================

class APIError(Exception):
    """Base exception for API errors."""
    pass


class AuthenticationError(APIError):
    """Raised when authentication fails (invalid/expired token)."""
    pass


class RateLimitError(APIError):
    """Raised when rate limit is exceeded."""
    pass


class ServerError(APIError):
    """Raised when server returns 5xx error."""
    pass


# =============================================================================
# API CLIENT CLASS
# =============================================================================

class APIClient:
    """
    HTTP client for OPUN8 backend API.

    Automatically handles:
        - JWT token injection in Authorization header
        - Token expiry (401) → auto-logout
        - Timeouts and connection errors with retries
        - JSON parsing of responses

    Attributes:
        base_url: Base URL of the API (including version prefix)
        timeout: Request timeout in seconds
        max_retries: Number of retries for failed requests
    """

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3
    ) -> None:
        """
        Initialize the API client.

        Args:
            timeout: Request timeout in seconds (default: 30)
            max_retries: Number of retry attempts (default: 3)
        """
        from opun8.config.constants import API_BASE_URL, API_VERSION
        self.base_url = f"{API_BASE_URL}/{API_VERSION}"
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_headers(self, custom_headers: Optional[Dict] = None) -> Dict[str, str]:
        """
        Build request headers with authentication token.

        Args:
            custom_headers: Additional headers to merge

        Returns:
            Dictionary of headers including Authorization if token exists
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OPUN8-CLI/1.0",
        }

        # Add token if available
        token = load_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Merge custom headers
        if custom_headers:
            headers.update(custom_headers)

        return headers

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Process API response and handle errors.

        Args:
            response: The HTTP response object

        Returns:
            Parsed JSON response as dictionary

        Raises:
            AuthenticationError: If token is invalid/expired (401)
            RateLimitError: If rate limit exceeded (429)
            ServerError: If server error occurs (5xx)
            APIError: For other error responses
        """
        # Parse JSON response safely
        try:
            data = response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
            # Some endpoints return plain text (e.g., /health)
            data = {"message": response.text}

        # Success
        if response.status_code == 200:
            return data

        # Extract error message safely
        if isinstance(data, dict):
            error_message = data.get("message") or data.get("error") or f"HTTP {response.status_code}"
        else:
            error_message = f"HTTP {response.status_code}"

        # Handle error status codes
        if response.status_code == 401:
            # Token expired or invalid → logout
            delete_token()
            raise AuthenticationError(f"Authentication failed: {error_message}")

        if response.status_code == 403:
            raise AuthenticationError(f"Permission denied: {error_message}")

        if response.status_code == 429:
            raise RateLimitError(f"Rate limit exceeded: {error_message}")

        if 500 <= response.status_code < 600:
            raise ServerError(f"Server error: {error_message}")

        raise APIError(f"Request failed: {error_message}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        retries: int = 0
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (e.g., /auth/login) OR full URL
            params: Query parameters
            data: JSON payload for POST/PUT requests
            headers: Custom headers
            retries: Current retry count (internal use)

        Returns:
            Parsed JSON response as dictionary

        Raises:
            APIError: If request fails after all retries
        """
        # ✅ FIX: If endpoint is already a full URL, use it directly
        # This prevents double-concatenation when backend_urls.py passes full URLs
        if endpoint.startswith(("http://", "https://")):
            url = endpoint
        else:
            url = f"{self.base_url}{endpoint}"

        request_headers = self._get_headers(headers)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                json=data,
                timeout=self.timeout,
            )
            return self._handle_response(response)

        except (Timeout, ConnectionError) as e:
            if retries < self.max_retries:
                return self._make_request(
                    method, endpoint, params, data, headers, retries + 1
                )
            raise APIError(f"Request failed after {self.max_retries} retries: {str(e)}")

        except RequestException as e:
            raise APIError(f"Request failed: {str(e)}")

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Send a GET request.

        Args:
            endpoint: API endpoint path OR full URL
            params: Query parameters

        Returns:
            Parsed JSON response

        Example:
            >>> client = APIClient()
            >>> user = client.get("/user/profile")
            >>> user = client.get("https://api.opun8.com/v1/user/profile")
        """
        return self._make_request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Send a POST request.

        Args:
            endpoint: API endpoint path OR full URL
            data: JSON payload

        Returns:
            Parsed JSON response

        Example:
            >>> client = APIClient()
            >>> result = client.post("/auth/login", data={"email": "...", "password": "..."})
            >>> result = client.post("https://api.opun8.com/v1/auth/login", data={...})
        """
        return self._make_request("POST", endpoint, data=data)

    def put(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Send a PUT request.

        Args:
            endpoint: API endpoint path OR full URL
            data: JSON payload

        Returns:
            Parsed JSON response
        """
        return self._make_request("PUT", endpoint, data=data)

    def delete(self, endpoint: str) -> Dict[str, Any]:
        """
        Send a DELETE request.

        Args:
            endpoint: API endpoint path OR full URL

        Returns:
            Parsed JSON response

        Example:
            >>> client = APIClient()
            >>> result = client.delete("/clones/abc123")
            >>> result = client.delete("https://api.opun8.com/v1/clones/abc123")
        """
        return self._make_request("DELETE", endpoint)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_client: Optional[APIClient] = None


def get_client() -> APIClient:
    """
    Get or create the global API client instance.

    Returns:
        APIClient singleton instance

    Example:
        >>> client = get_client()
        >>> user = client.get("/user/profile")
    """
    global _client
    if _client is None:
        _client = APIClient()
    return _client


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "APIClient",
    "get_client",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "ServerError",
]