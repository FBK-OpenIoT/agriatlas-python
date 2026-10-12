"""Authenticated STAC client and download helper for AgriAtlas (https://www.agriatlas.eu/)."""

from importlib.metadata import version

from ._default import current_session, download, download_asset, get_session, login, logout
from .config import AgriAtlasConfig
from .exceptions import (
    AgriAtlasError,
    AuthenticationError,
    NotLoggedInError,
    NotTrustedHostError,
)
from .session import AgriAtlasSession

__version__ = version("agriatlas")

__all__ = [
    "AgriAtlasConfig",
    "AgriAtlasError",
    "AgriAtlasSession",
    "AuthenticationError",
    "NotLoggedInError",
    "NotTrustedHostError",
    "__version__",
    "current_session",
    "download",
    "download_asset",
    "get_session",
    "login",
    "logout",
]
