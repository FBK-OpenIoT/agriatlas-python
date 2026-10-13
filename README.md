# agriatlas-python
Python client for [AgriAtlas](https://www.agriatlas.eu) catalog.
This library provides a simple authenticated STAC client and a download helper in only one import.

## Installation

The library is installed from GitHub, pinned to a release tag. Requires Python 3.11 or later.

```bash
uv add "agriatlas @ git+https://github.com/FBK-OpenIoT/agriatlas-python@v0.1.0"
```

With pip:

```bash
pip install "agriatlas @ git+https://github.com/FBK-OpenIoT/agriatlas-python@v0.1.0"
```

In a Jupyter notebook:

```python
%pip install "agriatlas @ git+https://github.com/FBK-OpenIoT/agriatlas-python@v0.1.0"
```

## Quick Usage

```python
import agriatlas

stac_client = agriatlas.login("<username>", "<password>")
item = stac_client.get_collection("<collection-id>").get_item("<item-id>")

files = agriatlas.download(item, "./data")  # {asset_key: Path} for the "data" assets
```

In addition, it is possible to download a single asset
```python
path = agriatlas.download_asset(item.assets["<asset-key>"], "./data/file.parquet")
```

or all the assets regardless of their role
```python
all_files = agriatlas.download(item, "./data", roles=None)
```

Downloads are verified against the asset's `file:checksum` when the catalog provides it. Files
already present with the expected checksum (or size, if there is no checksum) are not downloaded
again.

To check which account you are logged in with, ask Keycloak for the user information:
```python
info = agriatlas.get_session().get_user_info()  # e.g. {"preferred_username": ..., "email": ...}
```

Downloads show a progress bar and log messages. Pass `verbose=False` to hide them, e.g. in scripts:
```python
files = agriatlas.download(item, "./data", verbose=False)
```

For security, the access token is only sent to trusted hosts (by default `www.agriatlas.eu` and
`minio.services.irritre.openiotlab.eu`). A STAC request or a download to any other host raises
`agriatlas.NotTrustedHostError`. The host of the STAC API URL is always trusted, so pointing
`AGRIATLAS_STAC_API_URL` to another server works without changing the trusted hosts. To change the
trusted hosts, set `AGRIATLAS_TRUSTED_HOSTS` to a comma-separated list, or pass a custom config. A
custom list replaces the defaults, so include every host the files are stored on:

```python
config = agriatlas.AgriAtlasConfig(
    trusted_hosts={"minio.services.irritre.openiotlab.eu", "www.agriatlas.eu"}
)
stac_client = agriatlas.login(client_config=config)
```

The token is only sent over `https`. For a local development server on plain `http`, allow it
explicitly, knowing the token then travels unencrypted (or set `AGRIATLAS_ALLOW_HTTP=true`):

```python
config = agriatlas.AgriAtlasConfig(stac_api_url="http://localhost:8080/stac/", allow_http=True)
stac_client = agriatlas.login(client_config=config)
```

The `login()` function returns a [`pystac_client.Client`](https://pystac-client.readthedocs.io/) that is already authenticated: search, browse collections and items as usual. The access token is refreshed automatically before it expires. The full PySTAC Client Documentation can be found [HERE](https://pystac-client.readthedocs.io/).

## Getting started notebook

[`examples/getting_started.ipynb`](examples/getting_started.ipynb) walks through the whole flow in
Jupyter: it installs the library, logs in, opens an item and lists its assets, then downloads the
data files. To use it:

1. Open it in Jupyter, JupyterLab or VS Code.
2. Set `COLLECTION_ID` and `ITEM_ID` to the product you want to open.
3. Run the cells. `login()` prompts for your username and password, unless `AGRIATLAS_USERNAME`
   and `AGRIATLAS_PASSWORD` are set.

The files are saved in `./data`, next to the notebook.

## Python API

Everything below is importable from `agriatlas`. Each function and method has a docstring with the
details, e.g. `help(agriatlas.login)`.

### Functions

These work on a default session, created by `login()` and shared by the other functions.

| Function | Description |
|---|---|
| `login(username=None, password=None, *, client_config=None, interactive=True)` | Log in and return an authenticated `pystac_client.Client`. Replaces the previous default session only if the login succeeds. |
| `logout()` | Close the default session. Does nothing if not logged in. |
| `get_session()` | Return the default `AgriAtlasSession`. Raises `NotLoggedInError` if not logged in. |
| `current_session()` | Return the default `AgriAtlasSession`, or `None` if not logged in. |
| `download(item, target_path, *, roles=("data",), verbose=True)` | Download the assets of an Item into a directory. Returns `{asset_key: Path}`. |
| `download_asset(asset, target, *, verbose=True)` | Download one asset to a file. Returns its `Path`. |

`__version__` holds the installed version.

### Credentials

`login()` looks up the username and the password separately, in this order:

1. the `username` and `password` arguments;
2. the `AGRIATLAS_USERNAME` and `AGRIATLAS_PASSWORD` environment variables;
3. an interactive prompt. Pass `interactive=False` to raise `AuthenticationError` instead, e.g. in
   scripts that must not block.

### Configuration

`AgriAtlasConfig` holds the endpoints and options. `login()` uses `AgriAtlasConfig.from_env()` unless
you pass `client_config`. Each field can be set with an environment variable; empty values are
ignored.

| Field | Environment variable | Default |
|---|---|---|
| `stac_api_url` | `AGRIATLAS_STAC_API_URL` | `https://www.agriatlas.eu/api/stac/v1/` |
| `keycloak_url` | `AGRIATLAS_KEYCLOAK_URL` | `https://keycloak.azure.openiotlab.eu` |
| `keycloak_realm` | `AGRIATLAS_KEYCLOAK_REALM` | `agriatlas` |
| `keycloak_client_id` | `AGRIATLAS_KEYCLOAK_CLIENT_ID` | `agriatlas-cli` |
| `timeout` | `AGRIATLAS_TIMEOUT` | `60.0` seconds |
| `trusted_hosts` | `AGRIATLAS_TRUSTED_HOSTS` (comma-separated) | `www.agriatlas.eu`, `minio.services.irritre.openiotlab.eu` |
| `allow_http` | `AGRIATLAS_ALLOW_HTTP` (`true`/`false`) | `False` |

An invalid value, such as a non-numeric `AGRIATLAS_TIMEOUT`, raises `AgriAtlasError`.

### Sessions

`AgriAtlasSession` is what the functions above use behind the scenes. Create one yourself to work
without the global default, e.g. with several accounts or in tests:

```python
session = agriatlas.AgriAtlasSession(agriatlas.AgriAtlasConfig())
stac_client = session.login("<username>", "<password>")
files = session.download(item, "./data")
session.close()
```

| Method | Description |
|---|---|
| `login(username, password)` | Log in and return the authenticated STAC client. Both arguments are required: there is no env or prompt lookup here. |
| `close()` / `logout()` | Discard the tokens and close the HTTP connection. |
| `get_client()` | Return the STAC client. |
| `download(...)`, `download_asset(...)` | Same as the functions above. |
| `get_user_info()` | Return the user information from Keycloak, e.g. `preferred_username`, `name`, `email`. |
| `get_auth_headers()` | Return `{"Authorization": "Bearer <token>"}` with a valid token, for other tools. |

The methods raise `NotLoggedInError` before `login()` or after `close()`.

`get_auth_headers()` lets other HTTP clients, such as GDAL or rasterio, read AgriAtlas data:

```python
import os

headers = agriatlas.get_session().get_auth_headers()
os.environ["GDAL_HTTP_HEADERS"] = f"Authorization: {headers['Authorization']}"
```

The token expires, so call `get_auth_headers()` again before long jobs. These headers skip the
trusted-host check: only use them with AgriAtlas URLs.

### Exceptions

All the errors raised by the library derive from `AgriAtlasError`:

```
AgriAtlasError
├── AuthenticationError     login failed, token refused or expired, HTTP 403
│   └── NotLoggedInError    no login, or the session was closed; HTTP 401 on download
└── NotTrustedHostError     the token would go to an untrusted host, or over plain http
```

A download also raises `AgriAtlasError` when the asset is not found (HTTP 404) or its checksum does
not match.

## Development
To use the lib as developer, clone the repository then follow these steps
```bash
uv sync                                                            # create .venv with dev tools
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
uv run pytest                                                      # run the tests with coverage
uv run ruff check && uv run ruff format
```

Currently only a few tests are in place; more are planned. The `uv` definition already installs `pytest` and the other dev tools.

## License

[MIT](LICENSE), (C) 2026 OpenIoT Research Unit (Fondazione Bruno Kessler).

## Acknowledgement
TBD
