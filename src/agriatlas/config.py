"""Configuration of AgriAtlas Endpoints and options, with defaults overridable by environment
variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any

from .exceptions import AgriAtlasError


@dataclass(frozen=True)
class AgriAtlasConfig:
    """AgriAtlas client config for endpoints and options."""

    stac_api_url: str = "https://www.agriatlas.eu/api/stac/v1/"
    keycloak_url: str = "https://keycloak.azure.openiotlab.eu"
    keycloak_realm: str = "agriatlas"
    keycloak_client_id: str = "agriatlas-cli"
    timeout: float = 60.0

    @property
    def token_url(self) -> str:
        base = self.keycloak_url.rstrip("/")
        return f"{base}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @classmethod
    def from_env(cls) -> AgriAtlasConfig:
        """Create a config from environment variables."""
        values: dict[str, Any] = {}

        try:
            # Override the default values with environment variables if they exist
            for field in fields(cls):
                env_var = f"AGRIATLAS_{field.name.upper()}"
                value = os.getenv(env_var)

                # skip empty
                if value is None or not value.strip():
                    continue

                value = value.strip()

                if field.name == "timeout":
                    # Handle the timeout env variable
                    try:
                        values[field.name] = float(value)
                    except ValueError as err:
                        raise AgriAtlasError(f"Invalid value for {env_var}: {value!r}") from err

                else:
                    # Handle all other env variables
                    values[field.name] = value

        except Exception as e:
            # If any error occures while reading environment variables
            raise AgriAtlasError(f"Error reading environment variables: {e}") from e

        return cls(**values)
