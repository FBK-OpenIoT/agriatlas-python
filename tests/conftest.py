from unittest.mock import MagicMock

import pytest

from agriatlas import AgriAtlasConfig, AgriAtlasSession


@pytest.fixture
def session():
    # Logged-in session with a fake token manager: no Keycloak involved
    session = AgriAtlasSession(AgriAtlasConfig())
    session._token_manager = MagicMock()
    session._token_manager.get_auth_headers.return_value = {"Authorization": "Bearer T"}
    return session
