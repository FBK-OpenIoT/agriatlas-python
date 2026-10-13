import pystac
import pytest
import requests

import agriatlas
from agriatlas import AgriAtlasConfig, AgriAtlasSession, NotLoggedInError

TRUSTED_URL = "https://www.agriatlas.eu/files/field.parquet"


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
