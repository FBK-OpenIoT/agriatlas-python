"""The authenticated AgriAtlasSession to AgriAtlas, the login and logout functionalities"""

from __future__ import annotations

import logging
from pathlib import Path

import pystac
import requests
from pystac_client import Client

from .auth import TokenManager
from .auth_stac import AgriAtlasStacApiIO
from .config import AgriAtlasConfig
from .exceptions import NotLoggedInError

logger = logging.getLogger("agriatlas")


class AgriAtlasSession:
    """An authenticated AgriAtlas AgriAtlasSession that holds a pySTAC client, and the tokens it
    uses.

    Create one with `agriatlas.login()`.
    """

    _client_config: AgriAtlasConfig
    _http_session: requests.Session | None
    _stac_client: Client | None
    _token_manager: TokenManager | None

    def __init__(self, client_config: AgriAtlasConfig) -> None:
        self._client_config = client_config
        self._http_session = None
        self._stac_client = None
        self._token_manager = None

    def __repr__(self) -> str:
        return f"<agriatlas.Session stac_url={self._client_config.stac_api_url!r}, \
            username=TBD>"

    def login(self, username: str | None = None, password: str | None = None) -> Client:
        # before login, clear the clients and recreate them
        self.close()
        self._http_session = requests.Session()
        # all the login logic is handled here

        # Here all the login logic is handled with Username/Password
        # token manager here!
        self._token_manager = TokenManager.password_grant(
            config=self._client_config,
            http_session=self._http_session,
            username=username,
            password=password,
        )
        # Forget password by deallocating it!
        password = ""
        del password

        # Create the stack client with auth
        self._stac_client = Client.open(
            url=self._client_config.stac_api_url,
            stac_io=AgriAtlasStacApiIO(),  # Capture HTTP errors
            request_modifier=self._add_auth_headers,
            timeout=self._client_config.timeout,
        )

        return self._stac_client

    def logout(self):
        self.close()

    def close(self):
        if self._token_manager is not None:
            self._token_manager.close()
            self._token_manager = None

        if self._http_session is not None:
            self._http_session.close()
            self._http_session = None

        if self._stac_client is not None:
            self._stac_client = None

    def get_client(self):
        if self._stac_client:
            return self._stac_client
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")

    def get_auth_headers(self) -> dict[str, str]:
        """Return ``{"Authorization": "Bearer ..."}`` with a valid token, e.g. for GDAL."""
        return self._token_manager.get_auth_headers()

    def _add_auth_headers(self, request: requests.Request) -> None:
        request.headers.update(self._token_manager.get_auth_headers())

    def download_asset(self, asset: pystac.Asset, target: Path, *, create_path: bool = True):
        """Download an asset from AgriAtlas and it places it in the target path"""

        # Get the expected asset size
        expected_size = asset.extra_fields.get("file:size")
        if target.exists() and (expected_size is None or target.stat().st_size == expected_size):
            # If file present, skip download
            # TODO: add checksum verification to avoid download
            return target

        # Create the path tree if required
        if create_path:
            target.parent.mkdir(parents=True, exist_ok=True)

        # Start the request with active session
        response = self._http_session.get(
            asset.href,
            headers=self.get_auth_headers(),
            stream=True,
            timeout=60,
        )
        if response.status_code == 401:
            raise NotLoggedInError(f"HTTP 401 - Impossible to download {asset.href}")
        with response:
            response.raise_for_status()
            with open(target, "wb") as f:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        return target

    def download(
        self,
        item: pystac.Item,
        target_path: Path,
        *,
        roles: list[str] = frozenset(["data"]),
        create_path: bool = True,
    ):
        """Download all the assets associated to an Item with roles."""

        if roles is None:
            roles = []

        assets_path = {}
        for key, asset in item.assets.items():
            if not any(role in (asset.roles or []) for role in roles):
                # No role matching with asset.roles
                continue
            target = target_path / asset.href.rsplit("/", 1)[-1]
            assets_path[key] = self.download_asset(asset, target, create_path=create_path)

        return assets_path
