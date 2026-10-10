from typing import Any

from pystac_client.exceptions import APIError
from pystac_client.stac_api_io import StacApiIO

from .exceptions import AuthenticationError


class AgriAtlasStacApiIO(StacApiIO):
    """AgriAtlasStacApiIO overrides StacApiIO to capture authentication errors by overriding the
    request() method.
    """

    def request(
        self,
        href: str,
        method: str | None = None,
        headers: dict[str, str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        try:
            print("Href: ", href)
            print("method: ", method)
            print("headers: ", headers)
            print("parameters: ", parameters)
            return super().request(href, method=method, headers=headers, parameters=parameters)
        except APIError as err:
            if isinstance(err.__context__, AuthenticationError):
                raise err.__context__ from None
            status = getattr(err, "status_code", None)

            # Properly capture 401/403 error for AgriAtlas
            if status in (401, 403):
                raise AuthenticationError(
                    f"AgriAtlas refused access (HTTP {status}) to {href}"
                ) from err
            raise
