import getpass
import os
from typing import Any

import requests

from .exceptions import AuthenticationError


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


def parse_keycloak_error(response: requests.Response) -> str:
    """Parse the error message from a Keycloak response."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        message = body.get("error_description") or body.get("error")
        if message:
            return str(message)
    return f"http_session {response.status_code}"


def compute_token_expiration_deadline(now: float, seconds: Any) -> float | None:
    """Compute the expiration deadline from now + seconds"""
    # Keycloak reports 0 for tokens with no fixed expiry (e.g. offline tokens).
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return None
    return now + seconds if seconds > 0 else None
