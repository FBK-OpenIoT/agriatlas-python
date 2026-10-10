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
    token: str | None = None,
    interactive: bool = True,
) -> Client:
    global _default_logged_session

    # Get the config from env vars (if any is set)
    client_config = AgriAtlasConfig.from_env()

    # Note: Should this section be protected by try/except?
    # Create a new session
    session = AgriAtlasSession(client_config=client_config)

    if token is not None:
        # Login with token if provied
        session.login(token=token)
    else:
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

    return session.stac_client


def logout():
    """Log out by closing session"""
    if _default_logged_session is not None:
        _default_logged_session.close()


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
