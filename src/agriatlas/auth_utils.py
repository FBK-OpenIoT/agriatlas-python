import getpass
import os
from typing import Any

import requests

from .config import AgriAtlasConfig
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


def request_access_token(
    config: AgriAtlasConfig,
    http: requests.Session,
    credential_form: dict[str, Any],
    *,
    failure: str,
) -> dict[str, Any]:
    """Request an access token from Keycloak using the given form data."""

    credential_form = {"client_id": config.keycloak_client_id, **credential_form}

    try:
        # Send a POST request to the Keycloak token endpoint with the form data
        response = http.post(config.token_url, data=credential_form, timeout=config.timeout)
    except requests.RequestException as err:
        raise AuthenticationError(
            f"{failure}: could not reach {config.token_url} ({type(err).__name__})"
        ) from err

    # Handle keycloak error responses
    if not response.ok:
        raise AuthenticationError(f"{failure}: {parse_keycloak_error(response)}")
    try:
        return response.json()
    except ValueError as err:
        raise AuthenticationError(f"{failure}: Keycloak returned an invalid response") from err


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
    return f"HTTP {response.status_code}"


def compute_token_expiration_deadline(now: float, seconds: Any) -> float | None:
    """Compute the expiration deadline from now + seconds"""
    # Keycloak reports 0 for tokens with no fixed expiry (e.g. offline tokens).
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return None
    return now + seconds if seconds > 0 else None
