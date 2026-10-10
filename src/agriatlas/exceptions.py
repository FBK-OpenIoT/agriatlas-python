"""Exceptions raised by agriatlas library."""


class AgriAtlasError(Exception):
    """Base class for all agriatlas errors."""


class AuthenticationError(AgriAtlasError):
    """Login failed, a token could not be refreshed, or the server refused access."""


class NotLoggedInError(AuthenticationError):
    """An operation needs a session, but `login()` has not been called."""
