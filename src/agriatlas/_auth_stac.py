from typing import Any

from pystac_client.exceptions import APIError
from pystac_client.stac_api_io import StacApiIO

from .exceptions import AgriAtlasError, AuthenticationError


class AgriAtlasStacApiIO(StacApiIO):
    """AgriAtlasStacApiIO overrides StacApiIO to capture authentication errors by overriding the
    request() method.

    StacApiIO wraps any error raised by the request modifier in an APIError: agriatlas errors
    (failed token refresh, untrusted host) are unwrapped and raised as they are.
    """

    def request(
        self,
        href: str,
        method: str | None = None,
        headers: dict[str, str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        try:
            return super().request(href, method=method, headers=headers, parameters=parameters)
        except APIError as err:
            if isinstance(err.__context__, AgriAtlasError):
                raise err.__context__ from None
            status = getattr(err, "status_code", None)

            # Properly capture 401/403 error for AgriAtlas
            if status in (401, 403):
                raise AuthenticationError(
                    f"AgriAtlas refused access (HTTP {status}) to {href}"
                ) from err
            raise
