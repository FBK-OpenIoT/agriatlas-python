from unittest.mock import MagicMock

import pytest
import requests
import responses

from agriatlas import AgriAtlasConfig, AuthenticationError
from agriatlas._auth import TokenManager


# Test that close() drops the HTTP session without closing it: its owner closes it
def test_close_does_not_close_http_session():
    http_session = MagicMock(spec=requests.Session)
    manager = TokenManager("T", config=AgriAtlasConfig(), http_session=http_session)
    manager.close()

    http_session.close.assert_not_called()
    assert manager._http_session is None


# Test that asking for a token after close() raises AuthenticationError
def test_token_after_close():
    manager = TokenManager("T", config=AgriAtlasConfig(), http_session=requests.Session())
    manager.close()

    with pytest.raises(AuthenticationError, match="closed"):
        manager.get_auth_headers()


# Test that a token request after close() raises AuthenticationError
def test_request_after_close():
    manager = TokenManager("T", config=AgriAtlasConfig(), http_session=requests.Session())
    manager.close()

    with pytest.raises(AuthenticationError, match="no HTTP session"):
        manager._request_access_token(
            manager._config, manager._http_session, {"grant_type": "password"}, failure="Failed"
        )


# Test that password_grant() returns a manager holding the received tokens
@responses.activate
def test_password_grant():
    config = AgriAtlasConfig()
    responses.post(
        config.token_url,
        json={"access_token": "A", "expires_in": 300, "refresh_token": "R"},
    )

    manager = TokenManager.password_grant(config, requests.Session(), "user", "secret")

    assert manager.get_auth_headers() == {"Authorization": "Bearer A"}
    assert manager.is_refreshable


# Test that a token response without an access token raises AuthenticationError
@responses.activate
def test_password_grant_without_access_token():
    config = AgriAtlasConfig()
    responses.post(config.token_url, json={"refresh_token": "R"})

    with pytest.raises(AuthenticationError, match="no access token"):
        TokenManager.password_grant(config, requests.Session(), "user", "secret")
