# agriatlas-python
Python client for [AgriAtlas](https://www.agriatlas.eu) catalog.
This library provides a simple authenticated STAC client and a download helper in only one import.

## Quick Usage

```python
import agriatlas

client = agriatlas.login()  # pystac_client.Client, already authenticated
item = catalog.get_collection("<collection-id>").get_item("<item-id>")

files = agriatlas.download(item, "./data")  # {asset_key: Path} for the "data" assets
```

The `login()` function returns a [`pystac_client.Client`](https://pystac-client.readthedocs.io/) that is already authenticated: search, browse collections and items as usual. The access token is refreshed automatically before it expires. The full PySTAC Client Documentation can be found [HERE](https://pystac-client.readthedocs.io/).

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

## Development
To use the lib as developer, clone the repository then follow these steps
```bash
uv sync                                                            # create .venv with dev tools
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
# uv run pytest                                                      # tests with coverage. NOT IN PLACE NOW.
uv run ruff check && uv run ruff format
```

Currently, tests are not in place but planned to be addedd later. The `uv` definition already installs the `pytest` lib for future releases.

## License

[MIT](LICENSE), (C) 2026 OpenIoT Research Unit (Fondazione Bruno Kessler).

## Acknowledgement
TBD
