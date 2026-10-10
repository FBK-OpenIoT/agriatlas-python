import pytest

import agriatlas
from agriatlas import NotLoggedInError


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
