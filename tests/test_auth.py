from unittest.mock import MagicMock

import pytest
import requests

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
    manager = TokenManager("", config=AgriAtlasConfig(), http_session=requests.Session())
    manager.close()

    with pytest.raises(AuthenticationError, match="no HTTP session"):
        manager._request_access_token({"grant_type": "password"}, failure="Login failed")
