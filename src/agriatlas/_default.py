import getpass
import os
from collections.abc import Sequence
from pathlib import Path

import pystac
from pystac_client import Client

from ._config import AgriAtlasConfig
from ._session import AgriAtlasSession
from .exceptions import AuthenticationError, NotLoggedInError

_default_logged_session: AgriAtlasSession | None = None


def login(
    username: str | None = None,
    password: str | None = None,
    *,
    client_config: AgriAtlasConfig | None = None,
    interactive: bool = True,
) -> Client:
    """Log in to AgriAtlas and return an authenticated STAC client.

    The new session becomes the default one used by `download()`, `download_asset()` and
    `get_session()`. The previous default session, if any, is closed, but only once the new login
    succeeds: if it fails, the previous session is kept.

    The username and the password are each looked up in this order: the argument, then the
    `AGRIATLAS_USERNAME`/`AGRIATLAS_PASSWORD` environment variables, then an interactive prompt.
    The access token is refreshed automatically before it expires.

    Args:
        username: The AgriAtlas username.
        password: The AgriAtlas password. It is only used for the login and is not kept.
        client_config: The endpoints and options to use. Defaults to `AgriAtlasConfig.from_env()`,
            which reads the `AGRIATLAS_*` environment variables.
        interactive: Whether to prompt for missing credentials. Pass `False` in scripts and
            notebooks that must not block on a prompt.

    Returns:
        A `pystac_client.Client` whose requests carry the access token.

    Raises:
        AuthenticationError: If the credentials are missing (with `interactive=False` or without
            a terminal), or if Keycloak rejects them or cannot be reached.
        AgriAtlasError: If an `AGRIATLAS_*` environment variable is invalid, e.g. a non-numeric
            `AGRIATLAS_TIMEOUT`.
    """
    global _default_logged_session

    # Get the config from env vars (if any is set)
    if client_config is None:
        client_config = AgriAtlasConfig.from_env()

    # Resolve credentials
    resolved_user, resolved_pass = resolve_credentials(
        username=username, password=password, interactive=interactive
    )

    # Create a new session and log in. On failure, the session closes itself and the previous
    # default session is kept
    session = AgriAtlasSession(client_config=client_config)
    session.login(username=resolved_user, password=resolved_pass)

    # Check if any previous session exists and replace with a new valid session
    # This storing of the default session is done only if the login was successful
    if _default_logged_session is not None:
        # Close the default previous session
        _default_logged_session.close()
    _default_logged_session = session

    return session.get_client()


def logout() -> None:
    """Log out of AgriAtlas by closing the default session created by `login()`.

    The tokens and the HTTP session are discarded. Afterwards, the STAC client returned by
    `login()`, `download()` and `download_asset()` raise `NotLoggedInError` until `login()` is
    called again. Sessions created directly with `AgriAtlasSession` are not affected. Calling it
    when not logged in does nothing.
    """
    global _default_logged_session

    if _default_logged_session is not None:
        _default_logged_session.close()
    _default_logged_session = None


def get_session() -> AgriAtlasSession:
    """Return the default AgriAtlasSession created by `login()`.

    Use it to reach what the STAC client does not expose, e.g. `get_auth_headers()` to pass the
    token to GDAL or rasterio, or `get_user_info()`. To check whether a login happened without
    raising, use `current_session()`.

    Returns:
        The logged-in default session.

    Raises:
        NotLoggedInError: If `login()` has not been called successfully, or after `logout()`.
    """
    if _default_logged_session is None:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")
    return _default_logged_session


def current_session() -> AgriAtlasSession | None:
    """Return the default AgriAtlasSession created by `login()`, or None if not logged in."""
    return _default_logged_session


def download_asset(
    asset: pystac.Asset,
    target: str | Path,
    *,
    as_file: bool | None = None,
    verbose: bool = True,
) -> Path:
    """Download a single asset of an Item to the given file or directory, using the default session.

    In a directory, the file is named after the last segment of the asset's URL path, without the
    query string. Missing parent directories are created. The download is verified against the
    asset's `file:checksum` when the catalog provides it. An existing file is not downloaded again
    if its checksum matches, or, without a checksum, if its size matches `file:size`; otherwise it
    is replaced.

    Args:
        asset: The asset to download, e.g. `item.assets["<asset-key>"]`.
        target: The path of the file to write if it has an extension (e.g.
            `"./data/file.parquet"`), otherwise of a directory to write it into (e.g. `"./data"`).
            An existing directory, or a path ending with a separator, is always a directory.
        as_file: `True` to always take `target` as the file (e.g. a name without extension),
            `False` to always take it as a directory, `None` to decide as described above.
        verbose: Whether to show the progress bar and the download log messages.

    Returns:
        The path of the downloaded file, as a `Path`.

    Raises:
        NotLoggedInError: If `login()` has not been called, or the server answers HTTP 401.
        AuthenticationError: If the server answers HTTP 403, or the token cannot be refreshed.
        NotTrustedHostError: If the asset is not on a trusted host. Nothing is sent.
        AgriAtlasError: If the asset is not found (HTTP 404) or its checksum does not match. A
            file that fails the checksum is discarded. Also if `target` is a directory and the
            asset's URL path names no file.
    """
    if _default_logged_session is not None:
        return _default_logged_session.download_asset(
            asset=asset, target=target, as_file=as_file, verbose=verbose
        )
    else:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")


def download(
    item: pystac.Item,
    target_path: str | Path,
    *,
    roles: Sequence[str] | None = ("data",),
    verbose: bool = True,
) -> dict[str, Path]:
    """Download the assets of an Item into a directory, using the default session.

    Each file is named after the last segment of the asset's URL path, without the query string.
    When several assets share a name, the asset key is added as a prefix. Each asset is downloaded
    and verified as in `download_asset()`, so files already present and complete are skipped.

    Args:
        item: The STAC Item whose assets to download.
        target_path: The directory to download into. It is created if missing.
        roles: Download only the assets with at least one of these roles. With `None`, download
            all the assets.
        verbose: Whether to show the progress bars and the download log messages.

    Returns:
        A dict mapping each downloaded asset key to its local `Path`.

    Raises:
        NotLoggedInError: If `login()` has not been called.
        AgriAtlasError: If two assets would be written to the same file, before anything is
            downloaded. Also any error from `download_asset()`.
    """
    if _default_logged_session is not None:
        return _default_logged_session.download(
            item=item, target_path=target_path, roles=roles, verbose=verbose
        )
    else:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")


def resolve_credentials(
    username: str | None, password: str | None, *, interactive: bool
) -> tuple[str, str]:
    """Utility to resolve and return (username, password) from the arguments, the environment, or
    a prompt.
    """

    # Get username and password from arguments or environment variables
    username = username or os.environ.get("AGRIATLAS_USERNAME") or None
    password = password or os.environ.get("AGRIATLAS_PASSWORD") or None

    # If both username and password are resolved, return them directly
    if username and password:
        return username, password

    if not interactive:
        # Raise an exception if no credentials are provided and interactive mode is disabled
        raise AuthenticationError(
            "No AgriAtlas credentials: pass username and password, "
            "or set AGRIATLAS_USERNAME and AGRIATLAS_PASSWORD"
        )

    # Prompt the user for username and password if not provided
    try:
        if not username:
            username = input("AgriAtlas username: ").strip()
        if not password:
            password = getpass.getpass("AgriAtlas password: ")
    except EOFError as err:
        raise AuthenticationError(
            "No AgriAtlas credentials and no terminal to ask for them: pass username and "
            "password, or set AGRIATLAS_USERNAME and AGRIATLAS_PASSWORD"
        ) from err

    # If either username or password is still missing, raise an exception
    if not username or not password:
        raise AuthenticationError("AgriAtlas username and password are required")

    # Now, username and password are resolved
    return username, password
