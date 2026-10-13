import pytest
import requests

from agriatlas import AuthenticationError
from agriatlas.auth import TokenManager
from agriatlas.config import AgriAtlasConfig


# Test that a token request after close() raises AuthenticationError
def test_request_after_close():
    manager = TokenManager("", config=AgriAtlasConfig(), http_session=requests.Session())
    manager.close()

    with pytest.raises(AuthenticationError, match="no HTTP session"):
        manager._request_access_token({"grant_type": "password"}, failure="Login failed")
