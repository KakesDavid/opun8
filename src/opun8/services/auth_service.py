"""
Authentication Service
======================

Handles user authentication with the OPUN8 backend.

This module manages:
    - User registration with email verification
    - User login with JWT token issuance
    - OTP verification for email confirmation
    - Password resets (planned)
    - User profile retrieval

All authentication data (email, password hash, plan) is stored on the Render
backend. Only the JWT token is stored locally.

Why This File Exists:
    - Centralizes all auth logic in one place
    - Handles API calls to auth endpoints
    - Manages token storage via token_manager
    - Provides clean interface for CLI commands

Usage:
    from opun8.services.auth_service import AuthService

    auth = AuthService()
    result = auth.register("user@example.com", "username", "password")
    result = auth.login("user@example.com", "password")
    result = auth.verify_otp("user@example.com", "123456")

Author: OPUN8 Team
Version: 1.0.0
"""

from typing import Optional, Dict, Any
from opun8.services.api_client import get_client, AuthenticationError, APIError
from opun8.services.token_manager import save_token, delete_token, is_authenticated, load_token
from opun8.services.backend_urls import (
    AUTH_REGISTER,
    AUTH_LOGIN,
    AUTH_VERIFY_OTP,
    AUTH_RESEND_OTP,
    AUTH_LOGOUT,
    USER_PROFILE,
    USER_LIMITS,
)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class AuthError(Exception):
    """Base exception for authentication errors."""
    pass


class RegistrationError(AuthError):
    """Raised when registration fails."""
    pass


class LoginError(AuthError):
    """Raised when login fails."""
    pass


class OTPError(AuthError):
    """Raised when OTP verification fails."""
    pass


# =============================================================================
# AUTH SERVICE CLASS
# =============================================================================

class AuthService:
    """
    Authentication service for OPUN8.

    Handles all user authentication operations including registration,
    login, email verification, and logout.

    Attributes:
        client: API client instance for making HTTP requests
    """

    def __init__(self) -> None:
        """Initialize the authentication service."""
        self.client = get_client()

    # =========================================================================
    # REGISTRATION
    # =========================================================================

    def register(self, email: str, username: str, password: str) -> Dict[str, Any]:
        """
        Register a new user account.

        Args:
            email: User's email address
            username: Desired username
            password: User's password

        Returns:
            Dictionary containing:
                - message: Success message
                - email: Registered email
                - requires_verification: True if OTP sent

        Raises:
            RegistrationError: If registration fails

        Example:
            >>> auth = AuthService()
            >>> result = auth.register("user@example.com", "johndoe", "secure123")
            >>> print(result["message"])
            "Verification code sent to user@example.com"
        """
        try:
            response = self.client.post(
                AUTH_REGISTER,
                data={
                    "email": email,
                    "username": username,
                    "password": password,
                }
            )
            return response

        except APIError as e:
            raise RegistrationError(f"Registration failed: {str(e)}")

    # =========================================================================
    # LOGIN
    # =========================================================================

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Log in to OPUN8.

        Args:
            email: User's email address
            password: User's password

        Returns:
            Dictionary containing:
                - token: JWT token (saved locally)
                - user: User profile data
                - plan: User's subscription plan
                - clones_remaining: Number of clones left

        Raises:
            LoginError: If login fails or no token is returned

        Example:
            >>> auth = AuthService()
            >>> result = auth.login("user@example.com", "secure123")
            >>> print(f"Welcome back, {result['user']['username']}!")
        """
        try:
            response = self.client.post(
                AUTH_LOGIN,
                data={
                    "email": email,
                    "password": password,
                }
            )

            # The backend response structure:
            # {
            #   "success": true,
            #   "data": {
            #     "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            #     "user": {...},
            #     "plan": "free",
            #     "clones_remaining": 3
            #   },
            #   "message": "Login successful"
            # }
            #
            # So the token is inside response["data"]["token"]

            # Extract token from the nested structure
            data = response.get("data", {})
            token = data.get("token")

            if token:
                save_token(token)
                # Return the full response with token at the top level for backward compatibility
                response["token"] = token
                # Also ensure user data is at top level for CLI display
                if "user" in data:
                    response["user"] = data["user"]
                if "plan" in data:
                    response["plan"] = data["plan"]
                if "clones_remaining" in data:
                    response["clones_remaining"] = data["clones_remaining"]
                return response
            else:
                # Backend returned 200 but no token — should not happen
                raise LoginError("Login succeeded but no token was returned")

        except APIError as e:
            raise LoginError(f"Login failed: {str(e)}")

    # =========================================================================
    # OTP VERIFICATION
    # =========================================================================

    def verify_otp(self, email: str, code: str) -> Dict[str, Any]:
        """
        Verify email with OTP code.

        Args:
            email: User's email address
            code: 6-digit verification code

        Returns:
            Dictionary containing verification status

        Raises:
            OTPError: If verification fails

        Example:
            >>> auth = AuthService()
            >>> result = auth.verify_otp("user@example.com", "123456")
            >>> print(result["message"])
            "Email verified successfully!"
        """
        try:
            response = self.client.post(
                AUTH_VERIFY_OTP,
                data={
                    "email": email,
                    "code": code,
                }
            )
            return response

        except APIError as e:
            raise OTPError(f"Verification failed: {str(e)}")

    def resend_otp(self, email: str) -> Dict[str, Any]:
        """
        Resend OTP verification code.

        Args:
            email: User's email address

        Returns:
            Dictionary containing status message

        Raises:
            OTPError: If resend fails

        Example:
            >>> auth = AuthService()
            >>> result = auth.resend_otp("user@example.com")
            >>> print(result["message"])
            "New verification code sent!"
        """
        try:
            response = self.client.post(
                AUTH_RESEND_OTP,
                data={"email": email}
            )
            return response

        except APIError as e:
            raise OTPError(f"Failed to resend code: {str(e)}")

    # =========================================================================
    # LOGOUT
    # =========================================================================

    def logout(self) -> Dict[str, Any]:
        """
        Log out of OPUN8.

        Deletes the local JWT token and optionally notifies the server.

        Returns:
            Dictionary containing logout status

        Example:
            >>> auth = AuthService()
            >>> result = auth.logout()
            >>> print(result["message"])
            "Logged out successfully"
        """
        # Check if user is authenticated
        if not is_authenticated():
            return {"message": "Already logged out", "status": "info"}

        # Notify server (optional, best effort)
        try:
            self.client.post(AUTH_LOGOUT)
        except (APIError, AuthenticationError):
            # Server logout failed, but we'll still delete local token
            pass

        # Always delete local token
        delete_token()

        return {"message": "Logged out successfully", "status": "success"}

    # =========================================================================
    # USER INFORMATION
    # =========================================================================

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user profile information.

        Returns:
            Dictionary containing:
                - id: User ID
                - email: User's email
                - username: Username
                - plan: Subscription plan
                - clones_used: Number of clones used
                - clones_limit: Maximum clones allowed
                - clones_remaining: Clones left

        Raises:
            AuthenticationError: If not logged in

        Example:
            >>> auth = AuthService()
            >>> user = auth.get_user_info()
            >>> print(f"Plan: {user['plan']}")
            >>> print(f"Clones remaining: {user['clones_remaining']}")
        """
        if not is_authenticated():
            raise AuthenticationError("Not logged in. Run: opun8 login")

        response = self.client.get(USER_PROFILE)
        # The backend returns: {"success": true, "data": {...}, "message": "..."}
        # Extract the data field
        return response.get("data", response)

    def get_limits(self) -> Dict[str, Any]:
        """
        Get user's clone limits.

        Returns:
            Dictionary containing:
                - clones_used: Number used
                - clones_limit: Maximum allowed
                - clones_remaining: Remaining clones
                - plan: Current plan

        Raises:
            AuthenticationError: If not logged in

        Example:
            >>> auth = AuthService()
            >>> limits = auth.get_limits()
            >>> print(f"{limits['clones_remaining']} clones remaining")
        """
        if not is_authenticated():
            raise AuthenticationError("Not logged in. Run: opun8 login")

        response = self.client.get(USER_LIMITS)
        # The backend returns: {"success": true, "data": {...}, "message": "..."}
        # Extract the data field
        return response.get("data", response)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def is_authenticated(self) -> bool:
        """
        Check if user is currently authenticated.

        Returns:
            True if logged in, False otherwise

        Example:
            >>> auth = AuthService()
            >>> if auth.is_authenticated():
            ...     print("User is logged in")
        """
        return is_authenticated()

    def get_token(self) -> Optional[str]:
        """
        Get the current JWT token.

        Returns:
            Token string if logged in, None otherwise
        """
        return load_token()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """
    Get or create the global auth service instance.

    Returns:
        AuthService singleton instance

    Example:
        >>> auth = get_auth_service()
        >>> auth.login("user@example.com", "password")
    """
    global _service
    if _service is None:
        _service = AuthService()
    return _service


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "AuthService",
    "get_auth_service",
    "AuthError",
    "RegistrationError",
    "LoginError",
    "OTPError",
]