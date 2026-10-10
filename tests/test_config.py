import pytest

from agriatlas import AgriAtlasConfig, AgriAtlasError


# Simple test to check if the default config is loaded correctly
def test_default_values():
    config = AgriAtlasConfig.from_env()
    assert config == AgriAtlasConfig()
    assert config.stac_api_url == "https://www.agriatlas.eu/api/stac/v1/"
    assert config.token_url == (
        "https://keycloak.azure.openiotlab.eu/realms/agriatlas/protocol/openid-connect/token"
    )
    assert config.keycloak_client_id == "agriatlas-cli"
    assert config.timeout == 60.0


# Test to check if the config can be overridden by environment variables
def test_env_overrides(monkeypatch):
    override_stac_api_url = "http://localhost:8080/api/stac/v1/"
    override_keycloak_url = "http://localhost:8081/"
    override_keycloak_realm = "another-realm"
    override_keycloak_client = "another-client"
    override_timeout = "5"

    monkeypatch.setenv("AGRIATLAS_STAC_API_URL", override_stac_api_url)
    monkeypatch.setenv("AGRIATLAS_KEYCLOAK_URL", override_keycloak_url)
    monkeypatch.setenv("AGRIATLAS_KEYCLOAK_REALM", override_keycloak_realm)
    monkeypatch.setenv("AGRIATLAS_KEYCLOAK_CLIENT_ID", override_keycloak_client)
    monkeypatch.setenv("AGRIATLAS_TIMEOUT", override_timeout)

    config = AgriAtlasConfig.from_env()

    assert config.stac_api_url == override_stac_api_url
    assert config.keycloak_url == override_keycloak_url
    assert config.keycloak_realm == override_keycloak_realm
    assert config.keycloak_client_id == override_keycloak_client
    assert config.timeout == 5.0

    assert config.token_url == (
        "http://localhost:8081/realms/another-realm/protocol/openid-connect/token"
    )


# Test if a invalid value is set for timeout
def test_invalid_timeout(monkeypatch):
    monkeypatch.setenv("AGRIATLAS_TIMEOUT", "soon")

    with pytest.raises(AgriAtlasError, match="AGRIATLAS_TIMEOUT"):
        AgriAtlasConfig.from_env()
