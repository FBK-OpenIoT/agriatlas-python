from typing import Any

import requests


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
