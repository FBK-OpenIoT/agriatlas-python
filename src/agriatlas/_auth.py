from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from ._auth_utils import compute_token_expiration_deadline, parse_keycloak_error
from ._config import AgriAtlasConfig
from .exceptions import AuthenticationError

logger = logging.getLogger("agriatlas")


class TokenManager:
    """Holds the access and refresh tokens and hands out a valid access token.

    The password is used once, for the password grant in `password_grant()`, and is not kept.
    """

    _access_token: str | None
    _http_session: requests.Session | None

    def __init__(
        self,
        access_token: str,
        *,
        expires_at: float | None = None,
        refresh_token: str | None = None,
        refresh_expires_at: float | None = None,
        refresh_margin: int = 30,
        config: AgriAtlasConfig,
        http_session: requests.Session,
    ) -> None:
        self._access_token = access_token
        self._expires_at = expires_at
        self._refresh_token = refresh_token
        self._refresh_expires_at = refresh_expires_at
        self._refresh_margin = refresh_margin
        self._config = config
        self._http_session = http_session
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"<TokenManager is_refreshable={self.is_refreshable}>"

    @property
    def is_refreshable(self) -> bool:
        return self._refresh_token is not None

    @classmethod
    def password_grant(
        cls, config: AgriAtlasConfig, http_session: requests.Session, username: str, password: str
    ) -> TokenManager:
        """Log in to Keycloak with a username and password. Requires the password grant."""

        # Request an access token and refresh token from Keycloak using the password grant type
        data = cls._request_access_token(
            config,
            http_session,
            # The openid scope is required by Keycloak's userinfo endpoint (get_user_info)
            {
                "grant_type": "password",
                "username": username,
                "password": password,
                "scope": "openid email profile",
            },
            failure="AgriAtlas login failed",
        )

        # Create the TokenManager from the received tokens
        manager = cls(**cls._parse_tokens(data), config=config, http_session=http_session)
        logger.info("Logged in to AgriAtlas as %s", username)

        return manager

    def get_bearer_token(self) -> str:
        """Return an access token valid for at least `refresh_margin` seconds, if refreshable."""
        with self._lock:
            if self._access_token is None:
                raise AuthenticationError(
                    "The AgriAtlas session is closed: call agriatlas.login() again"
                )
            expiring = (
                self._expires_at is not None
                and time.monotonic() + self._refresh_margin >= self._expires_at
            )
            if expiring and self.is_refreshable:
                self._refresh_access_token()
            return self._access_token

    def get_auth_headers(self) -> dict[str, str]:
        """Return the Authorization header with a valid access token."""
        return {"Authorization": f"Bearer {self.get_bearer_token()}"}

    def get_user_info(self) -> dict[str, Any]:
        """Return the logged-in user's information from the Keycloak userinfo endpoint.

        The keys depend on the Keycloak scopes, e.g. `sub`, `preferred_username`, `name` and
        `email`.
        """
        failure = "Could not retrieve the AgriAtlas user information"

        # Get the headers first: they raise if the manager is closed, and refresh the token
        headers = self.get_auth_headers()
        if self._http_session is None:
            raise AuthenticationError(f"{failure}: no HTTP session; call agriatlas.login() again")

        try:
            response = self._http_session.get(
                self._config.userinfo_url, headers=headers, timeout=self._config.timeout
            )
        except requests.RequestException as err:
            raise AuthenticationError(
                f"{failure}: could not reach {self._config.userinfo_url} ({type(err).__name__})"
            ) from err

        # Handle keycloak error responses
        if not response.ok:
            raise AuthenticationError(f"{failure}: {parse_keycloak_error(response)}")
        try:
            return response.json()
        except ValueError as err:
            raise AuthenticationError(f"{failure}: Keycloak returned an invalid response") from err

    def close(self) -> None:
        """Forget the tokens and drop the HTTP session.

        The HTTP session belongs to whoever passed it in (the AgriAtlasSession), which closes it.
        """
        self._access_token = None
        self._expires_at = 0
        self._refresh_token = None
        self._refresh_expires_at = 0
        self._http_session = None

    @staticmethod
    def _parse_tokens(data: dict[str, Any]) -> dict[str, Any]:
        """Return the access token, refresh token and their expiration times from a Keycloak
        token response, as keyword arguments for the constructor.
        """
        now = time.monotonic()

        try:
            access_token = data["access_token"]
        except KeyError as err:
            raise AuthenticationError("AgriAtlas-Keycloak returned no access token") from err

        return {
            "access_token": access_token,
            "expires_at": compute_token_expiration_deadline(now, data.get("expires_in")),
            "refresh_token": data.get("refresh_token"),
            "refresh_expires_at": compute_token_expiration_deadline(
                now, data.get("refresh_expires_in")
            ),
        }

    def _store_tokens(self, data: dict[str, Any]) -> None:
        """Locally store the access token, refresh token, and their expiration times."""
        tokens = self._parse_tokens(data)
        self._access_token = tokens["access_token"]
        self._expires_at = tokens["expires_at"]
        self._refresh_token = tokens["refresh_token"]
        self._refresh_expires_at = tokens["refresh_expires_at"]

    def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""

        # Check if the refresh token has expired. Raise an exception if true.
        if self._refresh_expires_at is not None and time.monotonic() >= self._refresh_expires_at:
            raise AuthenticationError(
                "The AgriAtlas session has expired: call agriatlas.login() again"
            )

        # Refresh the access token using the refresh token
        logger.debug("Refreshing the AgriAtlas access token")
        data = self._request_access_token(
            self._config,
            self._http_session,
            {"grant_type": "refresh_token", "refresh_token": self._refresh_token},
            failure="Could not refresh the AgriAtlas session; call agriatlas.login() again",
        )

        # Update tokens and expiration times
        self._store_tokens(data)

    @staticmethod
    def _request_access_token(
        config: AgriAtlasConfig,
        http_session: requests.Session | None,
        credential_form: dict[str, Any],
        *,
        failure: str,
    ) -> dict[str, Any]:
        """Request an access token from Keycloak using the given form data.

        Static, so that `password_grant()` can request the tokens before creating the manager.
        """

        # The HTTP session is gone once the manager is closed
        if http_session is None:
            raise AuthenticationError(f"{failure}: no HTTP session; call agriatlas.login() again")

        credential_form = {
            "client_id": config.keycloak_client_id,
            **credential_form,
        }

        try:
            # Send a POST request to the Keycloak token endpoint with the form data
            response = http_session.post(
                config.token_url, data=credential_form, timeout=config.timeout
            )
        except requests.RequestException as err:
            raise AuthenticationError(
                f"{failure}: could not reach {config.token_url} ({type(err).__name__})"
            ) from err

        # Handle keycloak error responses
        if not response.ok:
            raise AuthenticationError(f"{failure}: {parse_keycloak_error(response)}")
        try:
            return response.json()
        except ValueError as err:
            raise AuthenticationError(f"{failure}: Keycloak returned an invalid response") from err
