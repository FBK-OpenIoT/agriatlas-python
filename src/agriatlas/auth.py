from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from .auth_utils import compute_token_expiration_deadline, request_access_token
from .config import AgriAtlasConfig
from .exceptions import AuthenticationError

logger = logging.getLogger("agriatlas")


class TokenManager:
    """Holds the access and refresh tokens and hands out a valid access token.

    The password is used once, for the password grant in `password_grant()`, and is not kept.
    """

    def __init__(
        self,
        access_token: str,
        *,
        expires_at: float | None = None,
        refresh_token: str | None = None,
        refresh_expires_at: float | None = None,
        refresh_margin: int = 30,
        config: AgriAtlasConfig | None = None,
        http_session: requests.Session | None = None,
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
        data = request_access_token(
            config,
            http_session,
            {"grant_type": "password", "username": username, "password": password},
            failure="AgriAtlas login failed",
        )
        logger.info("Logged in to AgriAtlas as %s", username)

        # Create a TokenManager instance with the received tokens and return it
        manager = cls("", config=config, http_session=http_session)
        manager._store_tokens(data)

        return manager

    def get_bearer_token(self) -> str:
        """Return an access token valid for at least `REFRESH_MARGIN` seconds, if refreshable."""
        with self._lock:
            expiring = (
                self._expires_at is not None
                and time.monotonic() + self._refresh_margin >= self._expires_at
            )
            if expiring and self.refreshable:
                self._refresh_access_token()
            return self._access_token

    def get_auth_headers(self) -> dict[str, str]:
        """Return the Authorization header with a valid access token."""
        return {"Authorization": f"Bearer {self.get_bearer_token()}"}

    def _store_tokens(self, data: dict[str, Any]) -> None:
        """Locally store the access token, refresh token, and their expiration times."""
        now = time.monotonic()

        try:
            # Store the access token
            self._access_token = data["access_token"]
        except KeyError as err:
            raise AuthenticationError("AgriAtlas-Keycloak returned no access token") from err

        # Compute the expiration time for the access token
        self._expires_at = compute_token_expiration_deadline(now, data.get("expires_in"))

        # Store the refresh token
        self._refresh_token = data.get("refresh_token")

        # Compute the expiration time for the refresh token
        self._refresh_expires_at = compute_token_expiration_deadline(
            now, data.get("refresh_expires_in")
        )

    def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        assert self._settings is not None and self._http is not None

        # Check if the refresh token has expired. Raise an exception if true.
        if self._refresh_expires_at is not None and time.monotonic() >= self._refresh_expires_at:
            raise AuthenticationError(
                "The AgriAtlas session has expired: call agriatlas.login() again"
            )

        # Refresh the access token using the refresh token
        logger.debug("Refreshing the AgriAtlas access token")
        data = request_access_token(
            self._settings,
            self._http,
            {"grant_type": "refresh_token", "refresh_token": self._refresh_token},
            failure="Could not refresh the AgriAtlas session; call agriatlas.login() again",
        )

        # Update tokens and expiration times
        self._store_tokens(data)
