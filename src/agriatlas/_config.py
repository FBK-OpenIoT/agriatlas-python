"""Configuration of AgriAtlas Endpoints and options, with defaults overridable by environment
variables."""

from __future__ import annotations

import os
from collections.abc import Collection
from dataclasses import dataclass, fields
from typing import Any, Self
from urllib.parse import urlparse

from .exceptions import AgriAtlasError, NotTrustedHostError

# Accepted values for boolean environment variables, compared in lowercase
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class AgriAtlasConfig:
    """AgriAtlas client config for endpoints and options.

    `trusted_hosts` accepts a single host name, a comma-separated string of host names, or any
    collection of host names (list, tuple, set...). The access token is only sent to these hosts
    and to the host of `stac_api_url`, which is always trusted: a STAC request or a download to any
    other host raises `NotTrustedHostError`.

    The token is only sent over `https`. Set `allow_http=True` (or `AGRIATLAS_ALLOW_HTTP=true`) to
    also allow plain `http`, e.g. for a local development server: the token is then sent
    unencrypted.
    """

    stac_api_url: str = "https://www.agriatlas.eu/api/stac/v1/"
    keycloak_url: str = "https://keycloak.azure.openiotlab.eu"
    keycloak_realm: str = "agriatlas"
    keycloak_client_id: str = "agriatlas-cli"
    timeout: float = 60.0
    trusted_hosts: str | Collection[str] = frozenset(
        {"www.agriatlas.eu", "minio.services.irritre.openiotlab.eu"}
    )
    allow_http: bool = False

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

    @property
    def _effective_trusted_hosts(self) -> frozenset[str]:
        """The configured trusted hosts plus the host of `stac_api_url`, which is always trusted.

        Otherwise pointing `stac_api_url` to another server would fail every request until
        `trusted_hosts` was changed too. `urlparse().hostname` is already lowercase.
        """
        stac_host = urlparse(self.stac_api_url).hostname
        return self.trusted_hosts | {stac_host} if stac_host else self.trusted_hosts

    def _is_allowed_scheme(self, url: str) -> bool:
        """Return True if `url` uses https, or plain http when `allow_http` is set."""
        scheme = urlparse(url).scheme.lower()
        return scheme == "https" or (self.allow_http and scheme == "http")

    def is_trusted(self, url: str) -> bool:
        """Return True if the token may be sent to `url`.

        The host must be a trusted host or the host of `stac_api_url`, and the scheme must be https
        (or http, with `allow_http`).
        """
        host = urlparse(url).hostname
        return (
            host is not None
            and host.lower() in self._effective_trusted_hosts
            and self._is_allowed_scheme(url)
        )

    def check_trusted_host(self, url: str) -> None:
        """Raise NotTrustedHostError if the token may not be sent to `url`."""
        if self.is_trusted(url):
            return
        if not self._is_allowed_scheme(url):
            raise NotTrustedHostError(
                f"Refusing to send the AgriAtlas token to {url!r}: only https is allowed "
                "(set allow_http=True for local development)"
            )
        raise NotTrustedHostError(
            f"{urlparse(url).hostname or url!r} is not a trusted AgriAtlas host "
            f"(trusted: {', '.join(sorted(self._effective_trusted_hosts))})"
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

            elif field.name == "allow_http":
                # Handle the allow_http env variable: bool("false") would be True
                if value.lower() in _TRUE_VALUES:
                    values[field.name] = True
                elif value.lower() in _FALSE_VALUES:
                    values[field.name] = False
                else:
                    raise AgriAtlasError(
                        f"Invalid value for {env_var}: {value!r} (use true/false, 1/0, yes/no)"
                    )

            else:
                # Handle all other env variables (trusted_hosts is split by __post_init__)
                values[field.name] = value

        return cls(**values)
