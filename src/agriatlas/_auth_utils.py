import re
from typing import Any

import requests

# The error_description in a WWW-Authenticate header, e.g. `Bearer error_description="..."`
_WWW_AUTHENTICATE_DESCRIPTION = re.compile(r'error_description="([^"]*)"')


def parse_keycloak_error(response: requests.Response) -> str:
    """Parse the error message from a Keycloak response.

    The token endpoint puts it in the JSON body. Bearer-protected endpoints such as userinfo put it
    in the `WWW-Authenticate` header and send an empty body.
    """
    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        message = body.get("error_description") or body.get("error")
        if message:
            return str(message)
    match = _WWW_AUTHENTICATE_DESCRIPTION.search(response.headers.get("WWW-Authenticate", ""))
    if match and match.group(1):
        return f"HTTP {response.status_code} ({match.group(1)})"
    return f"HTTP {response.status_code}"


def compute_token_expiration_deadline(now: float, seconds: Any) -> float | None:
    """Compute the expiration deadline from now + seconds"""
    # Keycloak reports 0 for tokens with no fixed expiry (e.g. offline tokens).
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return None
    return now + seconds if seconds > 0 else None
