# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`agriatlas` is a small Python library (Python >= 3.11, `src/` layout, built with `uv_build`) that gives an
authenticated `pystac_client.Client` for the AgriAtlas STAC catalog, plus helpers to download Item assets.
Authentication is a Keycloak password grant with automatic token refresh.

## Commands

```bash
uv sync                                                    # create .venv with dev tools
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
uv run pytest                                              # all tests, with coverage (addopts in pyproject)
uv run pytest tests/test_config.py::test_env_overrides     # single test
uv run pytest --no-cov -q                                  # fast run without coverage
uv run ruff check --fix && uv run ruff format              # lint + format (line length 100)
```

Pre-commit runs ruff check/format, `uv-lock` (keeps `uv.lock` in sync with `pyproject.toml`), and basic
file checks. The pytest pre-push hook is currently commented out.

## Architecture

The public API is whatever `src/agriatlas/__init__.py` re-exports. The rest are internal modules.

There are two layers:

- **`_default.py`: global default session.** `login()` resolves credentials, creates an
  `AgriAtlasSession`, logs it in, and only then replaces (and closes) the previous module-level
  `_default_logged_session`. It returns the session's STAC client. `logout()`, `get_session()`,
  `current_session()`, `download()` and `download_asset()` all operate on that global.
- **`session.py`: `AgriAtlasSession`.** Owns one `requests.Session`, a `TokenManager` and the
  `pystac_client.Client`. `login()` always calls `close()` first and rebuilds everything. Downloads go
  through the same `requests.Session`.

How auth is wired into STAC requests:

- `Client.open(..., request_modifier=session._add_auth_headers, stac_io=AgriAtlasStacApiIO())`. Every
  STAC request calls `TokenManager.get_auth_headers()`, which refreshes the access token under a lock
  if it expires within `refresh_margin` seconds. Deadlines use `time.monotonic()`.
- `auth_stac.AgriAtlasStacApiIO` subclasses pystac-client's `StacApiIO`. It turns an `APIError` whose
  `__context__` is an `AuthenticationError` back into that error, for example when a token refresh
  fails inside the request modifier. It also maps HTTP 401/403 to `AuthenticationError`. This depends
  on pystac-client internals, so re-check it when upgrading pystac-client.
- `auth_utils.py` holds the Keycloak token POST (`request_access_token`), error parsing, expiry
  computation, and `resolve_credentials`. The credential lookup order is: arguments, then
  `AGRIATLAS_USERNAME`/`AGRIATLAS_PASSWORD`, then an interactive prompt (disabled by
  `interactive=False`).

Config: `AgriAtlasConfig` is a frozen dataclass. `from_env()` maps each field to the environment
variable `AGRIATLAS_<FIELD_NAME_UPPER>`: `STAC_API_URL`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`,
`KEYCLOAK_CLIENT_ID` and `TIMEOUT`. Empty values are ignored. A new field gets an env override
automatically, but non-string fields need explicit parsing in `from_env()`, as `timeout` has.

Exceptions: `AgriAtlasError` is the base class. `AuthenticationError` derives from it, and
`NotLoggedInError` derives from `AuthenticationError`. Raise these classes, not raw
`requests`/pystac errors, at API boundaries.

Downloads: `download(item, dir, roles=("data",))` picks the assets that have any matching role
(`roles=None` downloads all of them). It names each file after the last segment of `asset.href`. A
file is skipped if it exists and its size matches the asset's `file:size` (or if `file:size` is
missing).

## Conventions

- Keep `CHANGELOG.md` (Keep a Changelog, SemVer) updated under `[Unreleased]` for user-visible changes,
  and update the README when the public API changes.
- Tests use `pytest` with `monkeypatch` for env vars. `responses` is available in the dev group for
  mocking HTTP (Keycloak and STAC). Tests must never hit the real AgriAtlas/Keycloak endpoints.
- `examples/test_example.py` is the maintainer's personal scratch script. Ignore it.
- `data/` holds downloaded parquet files and must not be committed.
