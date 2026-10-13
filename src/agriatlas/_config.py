"""Configuration of AgriAtlas Endpoints and options, with defaults overridable by environment
variables."""

from __future__ import annotations

import os
from collections.abc import Collection
from dataclasses import dataclass, fields
from typing import Any, Self
from urllib.parse import urlparse

from .exceptions import AgriAtlasError, NotTrustedHostError


@dataclass(frozen=True)
class AgriAtlasConfig:
    """AgriAtlas client config for endpoints and options.

    `trusted_hosts` accepts a single host name, a comma-separated string of host names, or any
    collection of host names (list, tuple, set...). The access token is only sent to these hosts:
    a STAC request or a download to any other host raises `NotTrustedHostError`.
    """

    stac_api_url: str = "https://www.agriatlas.eu/api/stac/v1/"
    keycloak_url: str = "https://keycloak.azure.openiotlab.eu"
    keycloak_realm: str = "agriatlas"
    keycloak_client_id: str = "agriatlas-cli"
    timeout: float = 60.0
    trusted_hosts: str | Collection[str] = frozenset(
        {"www.agriatlas.eu", "minio.services.irritre.openiotlab.eu"}
    )

    def __post_init__(self) -> None:
        # A string is a single host or a comma-separated list of hosts. Iterating over it directly
        # would trust each character ("w", ".", ...)
        hosts = self.trusted_hosts
        if isinstance(hosts, str):
            hosts = hosts.split(",")

        # Normalize to an immutable set of lowercase host names (host names are case-insensitive)
        hosts = frozenset(host.strip().lower() for host in hosts if host.strip())
        object.__setattr__(self, "trusted_hosts", hosts)

    @property
    def token_url(self) -> str:
        base = self.keycloak_url.rstrip("/")
        return f"{base}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @property
    def userinfo_url(self) -> str:
        base = self.keycloak_url.rstrip("/")
        return f"{base}/realms/{self.keycloak_realm}/protocol/openid-connect/userinfo"

    def is_trusted(self, url: str) -> bool:
        """Return True if the host of `url` is one of the trusted hosts."""
        host = urlparse(url).hostname
        return host is not None and host.lower() in self.trusted_hosts

    def check_trusted_host(self, url: str) -> None:
        """Raise NotTrustedHostError if the host of `url` is not a trusted host."""
        if not self.is_trusted(url):
            raise NotTrustedHostError(
                f"{urlparse(url).hostname or url!r} is not a trusted AgriAtlas host "
                f"(trusted: {', '.join(sorted(self.trusted_hosts))})"
            )

    @classmethod
    def from_env(cls) -> Self:
        """Create a config from environment variables."""
        values: dict[str, Any] = {}

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
                # Handle all other env variables (trusted_hosts is split by __post_init__)
                values[field.name] = value

        return cls(**values)
