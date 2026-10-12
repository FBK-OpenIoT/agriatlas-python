from unittest.mock import MagicMock

import pystac
import pytest
import responses

from agriatlas import AgriAtlasConfig, AgriAtlasSession, NotTrustedHostError
from agriatlas.auth_stac import AgriAtlasStacApiIO

TRUSTED_URL = "https://www.agriatlas.eu/files/a.bin"
UNTRUSTED_URL = "https://evil.example.com/files/a.bin"


@pytest.fixture
def session():
    # Logged-in session with a fake token manager: no Keycloak involved
    session = AgriAtlasSession(AgriAtlasConfig())
    session._token_manager = MagicMock()
    session._token_manager.get_auth_headers.return_value = {"Authorization": "Bearer T"}
    return session


# Test the default trusted hosts
def test_default_trusted_hosts():
    config = AgriAtlasConfig()
    assert config.trusted_hosts == frozenset(
        {"www.agriatlas.eu", "minio.services.irritre.openiotlab.eu"}
    )
    assert config.is_trusted("https://www.agriatlas.eu/api/stac/v1/")
    assert config.is_trusted("https://WWW.AgriAtlas.eu:443/x")


# Test URLs that look like a trusted host but are not
@pytest.mark.parametrize(
    "url",
    [
        "https://agriatlas.eu/x",
        "https://www.agriatlas.eu.evil.example.com/x",
        "https://evil.example.com/?www.agriatlas.eu",
        "https://www.agriatlas.eu@evil.example.com/x",
        "not a url",
    ],
)
def test_untrusted_urls(url):
    assert not AgriAtlasConfig().is_trusted(url)


# Test that any collection of hosts is accepted and normalized
@pytest.mark.parametrize(
    "hosts",
    [
        ["A.example.com", "b.example.com"],
        ("a.example.com", "b.example.com"),
        {"a.example.com", " B.example.com "},
    ],
)
def test_trusted_hosts_collections(hosts):
    config = AgriAtlasConfig(trusted_hosts=hosts)
    assert config.trusted_hosts == frozenset({"a.example.com", "b.example.com"})


# Test that a single string is a single host, not a collection of characters
def test_trusted_hosts_single_string():
    config = AgriAtlasConfig(trusted_hosts=" WWW.agriatlas.eu ")
    assert config.trusted_hosts == frozenset({"www.agriatlas.eu"})
    assert config.is_trusted(TRUSTED_URL)
    assert not config.is_trusted("https://w/")


# Test that a comma-separated string is split into hosts
def test_trusted_hosts_comma_string():
    config = AgriAtlasConfig(trusted_hosts="a.example.com, b.example.com,")
    assert config.trusted_hosts == frozenset({"a.example.com", "b.example.com"})


# Test the env override, comma-separated
def test_trusted_hosts_env(monkeypatch):
    monkeypatch.setenv("AGRIATLAS_TRUSTED_HOSTS", "a.example.com, b.example.com,")
    config = AgriAtlasConfig.from_env()
    assert config.trusted_hosts == frozenset({"a.example.com", "b.example.com"})


# Test check_trusted_host
def test_check_trusted_host():
    config = AgriAtlasConfig()
    config.check_trusted_host(TRUSTED_URL)
    with pytest.raises(NotTrustedHostError, match=r"evil\.example\.com"):
        config.check_trusted_host(UNTRUSTED_URL)


# Test that a STAC request to an untrusted host raises and sends nothing
@responses.activate
def test_stac_request_untrusted(session):
    stac_io = AgriAtlasStacApiIO(request_modifier=session._prepare_authenticated_request)
    with pytest.raises(NotTrustedHostError):
        stac_io.request(UNTRUSTED_URL)
    assert len(responses.calls) == 0


# Test that a STAC request to a trusted host carries the token
@responses.activate
def test_stac_request_trusted(session):
    responses.get(TRUSTED_URL, body="{}")
    stac_io = AgriAtlasStacApiIO(request_modifier=session._prepare_authenticated_request)
    stac_io.request(TRUSTED_URL)
    assert responses.calls[0].request.headers["Authorization"] == "Bearer T"


# Test that a download from an untrusted host raises and sends nothing
@responses.activate
def test_download_untrusted(session, tmp_path):
    with pytest.raises(NotTrustedHostError):
        session.download_asset(pystac.Asset(UNTRUSTED_URL), tmp_path / "a.bin")
    assert len(responses.calls) == 0
    assert not (tmp_path / "a.bin").exists()


# Test that a download from a trusted host carries the token
@responses.activate
def test_download_trusted(session, tmp_path):
    responses.get(TRUSTED_URL, body=b"abc")
    path = session.download_asset(pystac.Asset(TRUSTED_URL), tmp_path / "a.bin")
    assert path.read_bytes() == b"abc"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer T"
