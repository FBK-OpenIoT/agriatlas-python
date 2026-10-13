# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

- `agriatlas` is a small Python library (Python >= 3.11, `src/` layout, built with `uv_build`).
- It gives an authenticated `pystac_client.Client` for the AgriAtlas STAC catalog, plus helpers to
  download Item assets.
- Authentication is a Keycloak password grant with automatic token refresh.

## Commands

```bash
uv sync                                                    # create .venv with dev tools
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
uv run pytest                                              # all tests, with coverage (addopts in pyproject)
uv run pytest tests/test_config.py::test_env_overrides     # single test
uv run pytest --no-cov -q                                  # fast run without coverage
uv run ruff check --fix && uv run ruff format              # lint + format (line length 100)
```

- Pre-commit runs ruff check/format, `uv-lock` (keeps `uv.lock` in sync with `pyproject.toml`), and
  basic file checks.
- A pre-push hook runs `uv run pytest -q --no-cov`, so a failing test blocks `git push`.

## Architecture

The public API is whatever `src/agriatlas/__init__.py` re-exports. Every other module is internal and
named with a leading underscore (`_session.py`, `_auth.py`, ...), except `exceptions.py`, so that
exceptions show as `agriatlas.exceptions.X` in tracebacks; keep new modules that way.

### Layers

- **`_default.py`: global default session.**
  - `login()` resolves credentials, creates an `AgriAtlasSession`, logs it in, and only then
    replaces (and closes) the previous module-level `_default_logged_session`. It returns the
    session's STAC client.
  - `logout()`, `get_session()`, `current_session()`, `download()` and `download_asset()` all
    operate on that global.
- **`_session.py`: `AgriAtlasSession`.**
  - Owns one `requests.Session`, a `TokenManager` and the `pystac_client.Client`.
  - `login()` always calls `close()` first and rebuilds everything. On failure it closes itself.
  - After the password grant, `login()` fetches Keycloak's user info once and stores
    `preferred_username` for the `repr` (falling back to the login username if that request fails).
    `__repr__` must never send a request.

### Auth in STAC requests

- `Client.open(..., request_modifier=session._prepare_authenticated_request,
  stac_io=AgriAtlasStacApiIO())`.
- Every STAC request calls `TokenManager.get_auth_headers()`, which refreshes the access token under
  a lock if it expires within `refresh_margin` seconds. Deadlines use `time.monotonic()`.
- `_auth_stac.AgriAtlasStacApiIO` subclasses pystac-client's `StacApiIO`:
  - It turns an `APIError` whose `__context__` is an `AgriAtlasError` back into that error, for
    example when a token refresh fails or the host is not trusted inside the request modifier.
  - It maps HTTP 401/403 to `AuthenticationError`.
  - It depends on pystac-client internals, so re-check it when upgrading pystac-client.
- The Keycloak token POST is `TokenManager._request_access_token` in `_auth.py`.
- The password grant asks for `scope=openid`: without it, Keycloak's userinfo endpoint answers 403
  (`insufficient_scope`). Bearer endpoints report errors in the `WWW-Authenticate` header, not in
  the body, so `parse_keycloak_error` reads both.
- `_auth_utils.py` holds the helpers `parse_keycloak_error` and `compute_token_expiration_deadline`.
- `resolve_credentials` in `_default.py` looks up credentials in this order: arguments, then
  `AGRIATLAS_USERNAME`/`AGRIATLAS_PASSWORD`, then an interactive prompt (disabled by
  `interactive=False`).

### Config

- `AgriAtlasConfig` is a frozen dataclass.
- `from_env()` maps each field to the environment variable `AGRIATLAS_<FIELD_NAME_UPPER>`:
  `STAC_API_URL`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `TIMEOUT`,
  `TRUSTED_HOSTS` (comma-separated) and `ALLOW_HTTP` (true/false, 1/0, yes/no, on/off). Empty values
  are ignored.
- A new field gets an env override automatically, but non-string fields need explicit parsing in
  `from_env()`, as `timeout` and `allow_http` have.

### Trusted hosts

- `AgriAtlasConfig.trusted_hosts` takes a host, a comma-separated string or a collection;
  `__post_init__` normalizes it to a lowercase `frozenset`.
- The host of `stac_api_url` is always trusted too, through `_effective_trusted_hosts`, without being
  added to `trusted_hosts` itself.
- `check_trusted_host(url)` requires the exact hostname and the `https` scheme (or `http` with
  `allow_http`), or raises `NotTrustedHostError`. It runs before the token is attached, in
  `_prepare_authenticated_request` and `download_asset`. Any new code path that sends the token must
  call it too.
- The Keycloak token and userinfo URLs are not checked (they come from config, not catalog data).

### Exceptions

- `AgriAtlasError` is the base class.
- `AuthenticationError` and `NotTrustedHostError` derive from it, and `NotLoggedInError` derives from
  `AuthenticationError`.
- Raise these classes, not raw `requests`/pystac errors, at API boundaries.

### Downloads

- `download(item, dir, roles=("data",))` picks the assets that have any matching role (`roles=None`
  downloads all of them).
  - `_asset_filenames()` names each file after the last segment of the href's URL path, without
    the query string. It falls back to the asset key when that segment is empty, and prefixes the
    key when several assets share a name. It raises `AgriAtlasError` rather than overwrite a file.
- `download_asset()` downloads with `pooch.retrieve` (its own `requests.get`, not the session's
  `requests.Session`), passing the auth headers and the config timeout.
- Pooch writes to a temp file, creates missing directories, and shows a tqdm progress bar.
- The STAC `file:checksum` (hex multihash) is converted by `multihash_to_pooch_hash()` and passed as
  `known_hash`, so pooch verifies each download; a mismatch becomes `AgriAtlasError`.
- An existing file is skipped if its checksum matches, or, with no checksum, if its size matches
  `file:size` (or `file:size` is missing). Otherwise it is deleted first, because pooch never
  re-downloads a file that exists without a hash.
- HTTP 401, 403 and 404 become `NotLoggedInError`, `AuthenticationError` and `AgriAtlasError`.
- Pooch logging: during each download, a temporary filter on pooch's logger always drops its
  "known_hash" hint, and `verbose=False` adds one that drops all INFO messages and disables the
  progress bar.
  - Use filters, not `setLevel()`: pooch creates its logger outside the logging manager, so
    `setLevel()` doesn't reset its level cache.

## Conventions

- Keep `CHANGELOG.md` (Keep a Changelog, SemVer) updated under `[Unreleased]` for user-visible changes,
  and update the README when the public API changes.
- Tests use `pytest` with `monkeypatch` for env vars. `responses` is available in the dev group for
  mocking HTTP (Keycloak and STAC). Tests must never hit the real AgriAtlas/Keycloak endpoints.
- `examples/test_example.py` is the maintainer's personal scratch script. Ignore it.
- `data/` holds downloaded parquet files and must not be committed.
