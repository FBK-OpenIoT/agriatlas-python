import pystac
import pytest

from agriatlas import AgriAtlasError
from agriatlas._session import _asset_filenames


def _assets(**hrefs: str) -> dict[str, pystac.Asset]:
    return {key: pystac.Asset(href=href) for key, href in hrefs.items()}


# Test that the filename is the last segment of the URL path
def test_filename_from_href():
    assets = _assets(data="https://www.agriatlas.eu/files/field.parquet")
    assert _asset_filenames(assets) == {"data": "field.parquet"}


# Test that the query string and fragment are not part of the filename
def test_query_string_and_fragment_ignored():
    assets = _assets(data="https://www.agriatlas.eu/files/field.parquet?X-Amz-Signature=abc#part")
    assert _asset_filenames(assets) == {"data": "field.parquet"}


# Test that percent-encoded characters are decoded
def test_percent_encoding_decoded():
    assets = _assets(data="https://www.agriatlas.eu/files/my%20field.parquet")
    assert _asset_filenames(assets) == {"data": "my field.parquet"}


# Test that an encoded slash cannot escape the target directory
def test_encoded_slash_stays_in_directory():
    assets = _assets(data="https://www.agriatlas.eu/files/..%2F..%2Fescape.parquet")
    assert _asset_filenames(assets) == {"data": "escape.parquet"}


# Test that the asset key is used when the URL path has no filename
@pytest.mark.parametrize("href", ["https://www.agriatlas.eu/files/", "https://www.agriatlas.eu"])
def test_missing_filename_uses_key(href):
    assert _asset_filenames(_assets(data=href)) == {"data": "data"}


# Test that assets sharing a filename are prefixed with their asset key
def test_same_filename_prefixed_with_key():
    assets = _assets(
        red="https://www.agriatlas.eu/red/band.tif",
        nir="https://www.agriatlas.eu/nir/band.tif",
        meta="https://www.agriatlas.eu/meta.json",
    )
    assert _asset_filenames(assets) == {
        "red": "red_band.tif",
        "nir": "nir_band.tif",
        "meta": "meta.json",
    }


# Test that a collision left after prefixing raises instead of overwriting
def test_remaining_collision_raises():
    assets = _assets(
        a="https://www.agriatlas.eu/1/x.tif",
        b="https://www.agriatlas.eu/2/x.tif",
        c="https://www.agriatlas.eu/a_x.tif",
    )
    with pytest.raises(AgriAtlasError, match="same file"):
        _asset_filenames(assets)
