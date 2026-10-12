from collections.abc import Sequence
from pathlib import Path

import pystac
from pystac_client import Client

from .auth_utils import resolve_credentials
from .config import AgriAtlasConfig
from .exceptions import NotLoggedInError
from .session import AgriAtlasSession

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

    # Note: Should this section be protected by try/except?
    # Create a new session
    session = AgriAtlasSession(client_config=client_config)

    # Resolve credentials
    resolved_user, resolved_pass = resolve_credentials(
        username=username, password=password, interactive=interactive
    )

    # login with credentials
    session.login(username=resolved_user, password=resolved_pass)

    # Check if any previous session exists
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


def download_asset(asset: pystac.Asset, target: str | Path) -> Path:
    """Download an asset from AgriAtlas and place it in the target path.

    Returns the target path. Raises NotLoggedInError if `login()` has not been called.
    """
    if _default_logged_session:
        return _default_logged_session.download_asset(asset=asset, target=target)
    else:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")


def download(
    item: pystac.Item,
    target_path: str | Path,
    *,
    roles: Sequence[str] | None = ("data",),
) -> dict[str, Path]:
    """Download the assets of an Item into the target directory.

    Only assets with at least one of the given roles are downloaded; with `roles=None`, all the
    assets are. Returns a dict mapping each asset key to its local path. Raises NotLoggedInError
    if `login()` has not been called.
    """
    if _default_logged_session:
        return _default_logged_session.download(item=item, target_path=target_path, roles=roles)
    else:
        raise NotLoggedInError("Not logged in to AgriAtlas: call agriatlas.login() first")
