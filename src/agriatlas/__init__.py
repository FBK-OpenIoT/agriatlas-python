"""Authenticated STAC client and download helper for AgriAtlas (https://www.agriatlas.eu/)."""

from importlib.metadata import version

from .config import AgriAtlasConfig
from .exceptions import AgriAtlasError

__version__ = version("agriatlas")

__all__ = [
    "AgriAtlasConfig",
    "AgriAtlasError",
    "__version__",
]
