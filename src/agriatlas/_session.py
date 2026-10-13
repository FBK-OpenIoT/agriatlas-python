"""The authenticated AgriAtlasSession to AgriAtlas, the login and logout functionalities"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import pooch
import pystac
import requests
from pystac_client import Client

from ._auth import TokenManager
from ._auth_stac import AgriAtlasStacApiIO
from ._config import AgriAtlasConfig
from .exceptions import AgriAtlasError, AuthenticationError, NotLoggedInError

logger = logging.getLogger("agriatlas")

# Multihash codes (https://github.com/multiformats/multicodec) to hash names supported by pooch
_MULTIHASH_CODES = {0x11: "sha1", 0x12: "sha256", 0x13: "sha512", 0xD5: "md5"}


def _drop_below_warning(record: logging.LogRecord) -> bool:
    """Logging filter that keeps only warnings and errors."""
    return record.levelno >= logging.WARNING


def _drop_known_hash_hint(record: logging.LogRecord) -> bool:
    """Logging filter that drops pooch's hint to pass the hash as `known_hash` to pooch.retrieve.

    The hint is meant for pooch users and makes no sense to agriatlas users. Pooch only logs it
    when no hash is given, always with SHA256: match the `known_hash` part, which doesn't depend on
    the hash algorithm.
    """
    return "'known_hash' argument" not in str(record.msg)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Read an unsigned varint from data at pos, return (value, next position)."""
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def multihash_to_pooch_hash(checksum: str | None) -> str | None:
    """Convert a STAC `file:checksum` (hex-encoded multihash) to pooch's "<alg>:<hex>" format.

    Returns None if the checksum is missing or uses an unsupported/invalid encoding.
    """
    if not checksum:
        return None
    try:
        data = bytes.fromhex(checksum)
        code, pos = _read_varint(data, 0)
        length, pos = _read_varint(data, pos)
    except (ValueError, IndexError):
        logger.warning("Ignoring invalid file:checksum %r", checksum)
        return None

    digest = data[pos:]
    if code not in _MULTIHASH_CODES or len(digest) != length:
        logger.warning("Ignoring unsupported file:checksum %r", checksum)
        return None
    return f"{_MULTIHASH_CODES[code]}:{digest.hex()}"


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
        return f"<agriatlas.Session stac_url={self._client_config.stac_api_url!r}, username=TBD>"

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
            request_modifier=self._prepare_authenticated_request,
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

    def _prepare_authenticated_request(self, request: requests.Request) -> None:
        # Never send the token outside the trusted hosts
        self._client_config.check_trusted_host(request.url)

        # Add the authentication header
        request.headers.update(self._token_manager.get_auth_headers())

    def download_asset(
        self, asset: pystac.Asset, target: str | Path, *, verbose: bool = True
    ) -> Path:
        """Download an asset from AgriAtlas and place it in the target path.

        Missing parent directories are created. Returns the target path. An existing file with
        the expected checksum (or size, if the asset has no checksum) is not downloaded again.
        With `verbose=False`, the progress bar and pooch's log messages are hidden.
        """

        # Never send the token outside the trusted hosts
        self._client_config.check_trusted_host(asset.href)

        target = Path(target)

        # Get the expected asset size and checksum
        expected_size = asset.extra_fields.get("file:size")
        expected_checksum = multihash_to_pooch_hash(asset.extra_fields.get("file:checksum"))

        if target.exists():
            # If file present and complete, skip download. Use the checksum if available,
            # otherwise the size
            if expected_checksum is not None:
                if pooch.hashes.hash_matches(str(target), expected_checksum):
                    return target
            elif expected_size is None or target.stat().st_size == expected_size:
                return target

        # pooch skips files that already exist, so remove the incomplete one to download it again.
        # At this point, the existing file is corrupted/incomplete
        target.unlink(missing_ok=True)

        # Download to a temporary file, moved to the target once complete and verified
        downloader = pooch.HTTPDownloader(
            progressbar=verbose,
            chunk_size=1 << 20,
            headers=self.get_auth_headers(),
            timeout=self._client_config.timeout,
        )

        # pooch logs at INFO level through its own handler: always drop its "known_hash" hint, and
        # all the INFO messages if not verbose. Filters are used because pooch's logger is not
        # registered in the logging manager, so setLevel() would not reset its cached levels
        pooch_logger = pooch.get_logger()
        pooch_logger.addFilter(_drop_known_hash_hint)
        if not verbose:
            pooch_logger.addFilter(_drop_below_warning)

        try:
            pooch.retrieve(
                asset.href,
                known_hash=expected_checksum,
                fname=target.name,
                path=target.parent,
                downloader=downloader,
            )
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            if status == 401:
                raise NotLoggedInError(f"HTTP 401 - Impossible to download {asset.href}") from err
            if status == 403:
                raise AuthenticationError(f"HTTP 403 - Access denied to {asset.href}") from err
            if status == 404:
                raise AgriAtlasError(f"HTTP 404 - Asset not found at {asset.href}") from err
            raise
        except ValueError as err:
            # pooch raises ValueError if the hash does not match, and discards the file
            raise AgriAtlasError(f"Checksum mismatch for {asset.href}: {err}") from err
        finally:
            pooch_logger.removeFilter(_drop_known_hash_hint)
            pooch_logger.removeFilter(_drop_below_warning)
        return target

    def download(
        self,
        item: pystac.Item,
        target_path: str | Path,
        *,
        roles: Sequence[str] | None = ("data",),
        verbose: bool = True,
    ) -> dict[str, Path]:
        """Download the assets of an Item into the target directory.

        Only assets with at least one of the given roles are downloaded; with `roles=None`, all
        the assets are. Returns a dict mapping each asset key to its local path. With
        `verbose=False`, the progress bars and pooch's log messages are hidden.
        """

        # Accept str as well as Path
        target_path = Path(target_path)

        assets_path = {}
        for key, asset in item.assets.items():
            if roles is not None and not any(role in (asset.roles or []) for role in roles):
                # No role matching with asset.roles
                continue
            target = target_path / asset.href.rsplit("/", 1)[-1]
            assets_path[key] = self.download_asset(asset, target, verbose=verbose)

        return assets_path
