"""The authenticated AgriAtlasSession to AgriAtlas, the login and logout functionalities"""

from __future__ import annotations

import logging

import requests
from pystac_client import Client

from .auth import TokenManager
from .auth_stac import AgriAtlasStacApiIO
from .config import AgriAtlasConfig

logger = logging.getLogger("agriatlas")


class AgriAtlasSession:
    """An authenticated AgriAtlas AgriAtlasSession that holds a pySTAC client, and the tokens it
    uses.

    Create one with `agriatlas.login()`.
    """

    client_config: AgriAtlasConfig
    stac_client: Client
    token_manager: TokenManager

    def __init__(self, client_config: AgriAtlasConfig) -> AgriAtlasSession:

        self.client_config = client_config
        self._http_session = None
        self.stac_client = None
        self._token_manager = None

    def __repr__(self) -> str:
        return f"<agriatlas.Session stac_url={self.client_config.stac_api_url!r}, \
            username=TBD>"

    def login(
        self, username: str | None = None, password: str | None = None, *, token: str | None = None
    ) -> Client:
        # before login, clear the clients and recreate them
        self.close()
        self._http_session = requests.Session()
        # all the login logic is handled here

        if token is not None:
            # TODO: Introduce the direct Token handling
            raise NotImplementedError("Direct Token handling is NOT IMPLEMENTED YET!")

        # Here all the login logic is handled with Username/Password
        # token manager here!
        self._token_manager = TokenManager.password_grant(
            config=self.client_config,
            http_session=self._http_session,
            username=username,
            password=password,
        )
        # Forget password by deallocating it!
        password = ""
        del password

        # Create the stack client with auth
        self.stac_client = Client.open(
            url=self.client_config.stac_api_url,
            stac_io=AgriAtlasStacApiIO(),  # Capture HTTP errors
            request_modifier=self._add_auth_headers,
            timeout=self.client_config.timeout,
        )

        return self.stac_client

    def logout(self):
        self.close()

    def close(self):
        if self._http_session is not None:
            self._http_session.close()
            del self._http_session

        if self.stac_client is not None:
            del self.stac_client

    def get_auth_headers(self) -> dict[str, str]:
        """Return ``{"Authorization": "Bearer ..."}`` with a valid token, e.g. for GDAL."""
        return self._token_manager.get_auth_headers()

    def _add_auth_headers(self, request: requests.Request) -> None:
        print("TM: ", self._token_manager)
        request.headers.update(self._token_manager.get_auth_headers())
