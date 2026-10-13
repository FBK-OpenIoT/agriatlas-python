"""The authenticated AgriAtlasSession to AgriAtlas, the login and logout functionalities"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

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


def _href_filename(href: str) -> str:
    """Return the last segment of the URL path, without query string or fragment.

    Percent-encoded characters are decoded, so an encoded slash starts a new segment.
    """
    path = unquote(urlparse(href).path)
    # PurePosixPath drops a trailing slash, which means the URL names no file
    return "" if path.endswith("/") else PurePosixPath(path).name


def _asset_target_path(target: str | Path, href: str, as_file: bool | None = None) -> Path:
    """Return the file to download `href` to.

    With `as_file=None`, `target` is the file if it has an extension, unless it is an existing
    directory or ends with a path separator. `as_file=True` and `as_file=False` force a file or a
    directory. In a directory, the file is named after the last segment of the href's URL path.
    """
    path = Path(target)
    if as_file is None:
        # Check the string: Path() drops the trailing separator
        separators = tuple(sep for sep in (os.sep, os.altsep) if sep)
        as_file = bool(path.suffix) and not (path.is_dir() or str(target).endswith(separators))

    if as_file:
        # path to a file
        return path

    name = _href_filename(href)
    if name in ("", ".", ".."):
        raise AgriAtlasError(f"Cannot name the file to download from {href}: pass a file path")

    # append the filename to the path
    return path / name


def _asset_filenames(assets: dict[str, pystac.Asset]) -> dict[str, str]:
    """Map each asset key to the local filename to download it to.

    The filename is the last segment of the href's URL path. When it is empty or invalid, the
    asset key is used instead; when several assets share it, it is prefixed with the asset key.
    """
    # TODO: keep the folder tree of nested assets (e.g. .../2024/01/ndvi.tif) instead of flattening
    # it. Mirror each URL path below the common prefix of all the item's assets (not only the
    # selected ones, so the layout doesn't depend on `roles`), and reject `.`/`..` segments and
    # any path that resolves outside the target directory. Check a real nested item first.
    names = {}
    for key, asset in assets.items():
        name = _href_filename(asset.href)
        names[key] = name if name not in ("", ".", "..") else PurePosixPath(key).name

    # Prefix the asset key to the filenames that more than one asset would use
    counts = Counter(names.values())
    filenames = {
        key: f"{PurePosixPath(key).name}_{name}" if counts[name] > 1 else name
        for key, name in names.items()
    }

    # A prefixed filename can still match another asset's filename: never overwrite silently
    if len(set(filenames.values())) < len(filenames):
        raise AgriAtlasError("Several assets would be downloaded to the same file")
    return filenames


class AgriAtlasSession:
    """An authenticated AgriAtlas AgriAtlasSession that holds a pySTAC client, and the tokens it
    uses.

    Create one with `agriatlas.login()`.
    """

    _client_config: AgriAtlasConfig
    _http_session: requests.Session | None
    _stac_client: Client | None
    _token_manager: TokenManager | None
    _username: str | None

    def __init__(self, client_config: AgriAtlasConfig) -> None:
        self._client_config = client_config
        self._http_session = None
        self._stac_client = None
        self._token_manager = None
        self._username = None

    def __repr__(self) -> str:
        # Use the username stored at login: a repr must not send requests
        username = repr(self._username) if self._token_manager is not None else "Not Logged"
        return (
            f"<AgriAtlasSession stac_url={self._client_config.stac_api_url!r}, username={username}>"
        )

    def login(self, username: str, password: str) -> Client:
        # before login, clear the clients and recreate them
        self.close()
        self._http_session = requests.Session()
        # all the login logic is handled here

        try:
            # Here all the login logic is handled with Username/Password
            # token manager here!
            self._token_manager = TokenManager.password_grant(
                config=self._client_config,
                http_session=self._http_session,
                username=username,
                password=password,
            )

            # Store the username for the repr: the one Keycloak reports, or the one used to log in
            self._username = self._fetch_username(default=username)

            # Create the stack client with auth
            self._stac_client = Client.open(
                url=self._client_config.stac_api_url,
                stac_io=AgriAtlasStacApiIO(),  # Capture HTTP errors
                request_modifier=self._prepare_authenticated_request,
                timeout=self._client_config.timeout,
            )
        except BaseException:
            # Don't leak the HTTP session or stay half logged in if the login fails
            self.close()
            raise

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

        self._username = None

    def get_client(self):
        if self._stac_client:
            return self._stac_client
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")

    def _require_login(self) -> None:
        """Raise NotLoggedInError if not logged in."""
        if self._token_manager is None:
            raise NotLoggedInError("Not logged in to AgriAtlas: call login() first")

    def get_auth_headers(self) -> dict[str, str]:
        """Return ``{"Authorization": "Bearer ..."}`` with a valid token, e.g. for GDAL."""
        self._require_login()
        return self._token_manager.get_auth_headers()

    def _fetch_username(self, default: str) -> str:
        """Return the `preferred_username` from Keycloak's user info, or `default` if unavailable.

        The user info is only cosmetic here, so a failure doesn't fail the login.
        """
        try:
            username = self.get_user_info().get("preferred_username")
        except AuthenticationError as err:
            # The error message already says what failed
            logger.warning("%s", err)
            return default
        return username if isinstance(username, str) and username else default

    def get_user_info(self) -> dict[str, Any]:
        """Return the logged-in user's information from Keycloak, e.g. `preferred_username`,
        `name` and `email`.
        """
        self._require_login()
        return self._token_manager.get_user_info()

    def _prepare_authenticated_request(self, request: requests.Request) -> None:
        # Never send the token outside the trusted hosts
        self._client_config.check_trusted_host(request.url)

        # Add the authentication header
        request.headers.update(self.get_auth_headers())

    def download_asset(
        self,
        asset: pystac.Asset,
        target: str | Path,
        *,
        as_file: bool | None = None,
        verbose: bool = True,
    ) -> Path:
        """Download an asset from AgriAtlas and place it in the target path.

        `target` is the file to write if it has an extension, otherwise a directory (also if it
        exists as one or ends with a path separator), and the file is then named after the last
        segment of the asset's URL path. `as_file=True` or `as_file=False` forces a file or a
        directory. Missing parent directories are created. Returns the path
        of the file. An existing file with the expected checksum (or size, if the asset has no
        checksum) is not downloaded again. With `verbose=False`, the progress bar and pooch's log
        messages are hidden.
        """

        # Fail early, even if the file is already present and would not be downloaded
        self._require_login()

        # Never send the token outside the trusted hosts
        self._client_config.check_trusted_host(asset.href)

        target = _asset_target_path(target, asset.href, as_file)

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
            # pooch raises ValueError if the hash does not match, and discards the file. It also
            # raises ValueError for other problems (e.g. an unsupported hash algorithm), so check
            # the message to tell them apart
            if expected_checksum is not None and "does not match" in str(err):
                raise AgriAtlasError(f"Checksum mismatch for {asset.href}: {err}") from err
            raise AgriAtlasError(f"Could not download {asset.href}: {err}") from err
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

        # Keep only the assets with at least one matching role
        assets = {
            key: asset
            for key, asset in item.assets.items()
            if roles is None or any(role in (asset.roles or []) for role in roles)
        }

        assets_path = {}
        for key, filename in _asset_filenames(assets).items():
            # The filename may have no extension: don't let download_asset() take it as a directory
            assets_path[key] = self.download_asset(
                assets[key], target_path / filename, as_file=True, verbose=verbose
            )

        return assets_path
