import logging

import pystac
import pytest
import requests
import responses

import agriatlas
from agriatlas import AgriAtlasConfig, AgriAtlasSession, AuthenticationError, NotLoggedInError

TRUSTED_URL = "https://www.agriatlas.eu/files/field.parquet"
INVALID_GRANT = {"error": "invalid_grant", "error_description": "Invalid user credentials"}


# Test that a failed login closes the HTTP session it created and leaves the session logged out
@responses.activate
def test_login_failure_closes_http_session(monkeypatch):
    config = AgriAtlasConfig()
    responses.post(config.token_url, status=401, json=INVALID_GRANT)
    closed = []
    monkeypatch.setattr(requests.Session, "close", lambda self: closed.append(self))

    session = AgriAtlasSession(config)
    with pytest.raises(AuthenticationError):
        session.login("user", "wrong")

    assert len(closed) == 1
    assert session._http_session is None
    assert session._token_manager is None
    with pytest.raises(NotLoggedInError):
        session.get_client()


# Test that a failed agriatlas.login() keeps the previous default session
@responses.activate
def test_default_login_failure_keeps_previous_session(monkeypatch):
    config = AgriAtlasConfig()
    responses.post(config.token_url, status=401, json=INVALID_GRANT)
    previous = AgriAtlasSession(config)
    monkeypatch.setattr(agriatlas._default, "_default_logged_session", previous)

    with pytest.raises(AuthenticationError):
        agriatlas.login("user", "wrong", client_config=config, interactive=False)

    assert agriatlas.current_session() is previous


# Test if not logged in
def test_not_logged_in():
    assert agriatlas.current_session() is None
    with pytest.raises(NotLoggedInError):
        agriatlas.get_session()


# Test if correctly logged out
def test_logged_out():
    agriatlas.logout()

    assert agriatlas.current_session() is None
    with pytest.raises(NotLoggedInError):
        agriatlas.get_session()


# Test that a session that never logged in raises NotLoggedInError, not AttributeError
def test_session_not_logged_in():
    session = AgriAtlasSession(AgriAtlasConfig())

    with pytest.raises(NotLoggedInError):
        session.get_auth_headers()
    with pytest.raises(NotLoggedInError):
        session._prepare_authenticated_request(requests.Request("GET", TRUSTED_URL))


# Test that download_asset raises NotLoggedInError even if the file is already present
def test_download_asset_not_logged_in(tmp_path):
    session = AgriAtlasSession(AgriAtlasConfig())
    target = tmp_path / "field.parquet"
    target.write_bytes(b"data")

    with pytest.raises(NotLoggedInError):
        session.download_asset(pystac.Asset(href=TRUSTED_URL), target)


# Test that get_user_info() on a session that is not logged in raises NotLoggedInError
def test_get_user_info_not_logged_in():
    with pytest.raises(NotLoggedInError):
        AgriAtlasSession(AgriAtlasConfig()).get_user_info()


TOKENS = {"access_token": "A", "expires_in": 300, "refresh_token": "R"}


@pytest.fixture
def no_stac(monkeypatch):
    # login() opens the STAC client: skip it, so only Keycloak is mocked
    monkeypatch.setattr("agriatlas._session.Client.open", lambda *args, **kwargs: object())


# Test the repr of a session that is not logged in
def test_repr_not_logged_in():
    assert "username=Not Logged" in repr(AgriAtlasSession(AgriAtlasConfig()))


# Test that the repr shows the username from Keycloak's user info, and Not Logged after close()
@responses.activate
def test_repr_username_from_user_info(no_stac):
    config = AgriAtlasConfig()
    responses.post(config.token_url, json=TOKENS)
    responses.get(config.userinfo_url, json={"preferred_username": "keycloak-user"})
    session = AgriAtlasSession(config)

    session.login("user", "secret")
    assert "username='keycloak-user'" in repr(session)

    session.close()
    assert "username=Not Logged" in repr(session)


# Test that a user info failure doesn't fail the login, and the login username is shown instead
@responses.activate
def test_repr_username_without_user_info(no_stac, caplog):
    config = AgriAtlasConfig()
    responses.post(config.token_url, json=TOKENS)
    responses.get(config.userinfo_url, status=500)
    session = AgriAtlasSession(config)

    with caplog.at_level(logging.WARNING, logger="agriatlas"):
        session.login("user", "secret")
    assert "username='user'" in repr(session)
