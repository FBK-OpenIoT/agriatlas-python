import pystac
import pytest
import responses

from agriatlas import AgriAtlasConfig, AgriAtlasError, NotTrustedHostError
from agriatlas._auth_stac import AgriAtlasStacApiIO

TRUSTED_URL = "https://www.agriatlas.eu/files/a.bin"
UNTRUSTED_URL = "https://evil.example.com/files/a.bin"


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


# Test that the host of stac_api_url is always trusted, without changing trusted_hosts
def test_stac_host_always_trusted():
    config = AgriAtlasConfig(
        stac_api_url="http://LocalHost:8080/stac/",
        trusted_hosts="data.example.com",
        allow_http=True,
    )
    assert config.trusted_hosts == frozenset({"data.example.com"})
    assert config.is_trusted("http://localhost:8080/stac/collections")
    assert config.is_trusted("https://data.example.com/a.bin")
    assert not config.is_trusted("https://www.agriatlas.eu/a.bin")


# Test that the error message lists the host of stac_api_url among the trusted hosts
def test_untrusted_message_lists_stac_host():
    config = AgriAtlasConfig(
        stac_api_url="http://localhost:8080/stac/", trusted_hosts=(), allow_http=True
    )
    with pytest.raises(NotTrustedHostError, match=r"\(trusted: localhost\)"):
        config.check_trusted_host(UNTRUSTED_URL)


# Test that the token is never sent over plain http to a trusted host, unless allow_http is set
def test_http_rejected_by_default():
    config = AgriAtlasConfig()
    url = "http://www.agriatlas.eu/files/a.bin"
    assert not config.is_trusted(url)
    with pytest.raises(NotTrustedHostError, match="only https"):
        config.check_trusted_host(url)

    assert AgriAtlasConfig(allow_http=True).is_trusted(url)


# Test that allow_http allows only http, not other schemes, and still checks the host
@pytest.mark.parametrize(
    "url",
    ["ftp://www.agriatlas.eu/a.bin", "file://www.agriatlas.eu/a.bin", "http://evil.example.com/x"],
)
def test_allow_http_other_schemes(url):
    assert not AgriAtlasConfig(allow_http=True).is_trusted(url)


# Test that a plain http download sends nothing
@responses.activate
def test_download_over_http_rejected(session, tmp_path):
    with pytest.raises(NotTrustedHostError, match="only https"):
        session.download_asset(pystac.Asset("http://www.agriatlas.eu/a.bin"), tmp_path / "a.bin")
    assert len(responses.calls) == 0


# Test the AGRIATLAS_ALLOW_HTTP env variable
@pytest.mark.parametrize(("value", "expected"), [("true", True), ("Yes", True), ("0", False)])
def test_allow_http_env(monkeypatch, value, expected):
    monkeypatch.setenv("AGRIATLAS_ALLOW_HTTP", value)
    assert AgriAtlasConfig.from_env().allow_http is expected


# Test that an invalid AGRIATLAS_ALLOW_HTTP raises AgriAtlasError
def test_allow_http_env_invalid(monkeypatch):
    monkeypatch.setenv("AGRIATLAS_ALLOW_HTTP", "maybe")
    with pytest.raises(AgriAtlasError, match="AGRIATLAS_ALLOW_HTTP"):
        AgriAtlasConfig.from_env()
