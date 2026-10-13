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


def logout():
    """Log out by closing session"""
    global _default_logged_session

    if _default_logged_session is not None:
        _default_logged_session.close()
    _default_logged_session = None


def get_session() -> AgriAtlasSession:
    """Return the default AgriAtlasSession created by `login()`.

    Raises:
        NotLoggedInError: If `login()` has not been called successfully.
    """
    if _default_logged_session is None:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")
    return _default_logged_session


def current_session() -> AgriAtlasSession | None:
    """Return the default AgriAtlasSession created by `login()`, or None if not logged in."""
    return _default_logged_session


def download_asset(asset: pystac.Asset, target: str | Path, *, verbose: bool = True) -> Path:
    """Download an asset from AgriAtlas and place it in the target path.

    Returns the target path. With `verbose=False`, the progress bar and pooch's log messages are
    hidden. Raises NotLoggedInError if `login()` has not been called.
    """
    if _default_logged_session:
        return _default_logged_session.download_asset(asset=asset, target=target, verbose=verbose)
    else:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")


def download(
    item: pystac.Item,
    target_path: str | Path,
    *,
    roles: Sequence[str] | None = ("data",),
    verbose: bool = True,
) -> dict[str, Path]:
    """Download the assets of an Item into the target directory.

    Only assets with at least one of the given roles are downloaded; with `roles=None`, all the
    assets are. Returns a dict mapping each asset key to its local path. With `verbose=False`, the
    progress bars and pooch's log messages are hidden. Raises NotLoggedInError if `login()` has
    not been called.
    """
    if _default_logged_session:
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
