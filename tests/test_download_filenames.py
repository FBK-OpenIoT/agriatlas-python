import pystac
import pytest

from agriatlas import AgriAtlasError
from agriatlas._session import _asset_filenames, _asset_target_path

HREF = "https://www.agriatlas.eu/files/field.parquet?X-Amz-Signature=abc"


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


# Test that a target with an extension is the file to write
def test_target_with_extension_is_file(tmp_path):
    assert _asset_target_path(tmp_path / "out.bin", HREF) == tmp_path / "out.bin"
    assert _asset_target_path(str(tmp_path / "missing" / "out.bin"), HREF) == (
        tmp_path / "missing" / "out.bin"
    )


# Test that a target without an extension is a directory, even if missing
def test_target_without_extension_is_directory(tmp_path):
    assert _asset_target_path(tmp_path / "data", HREF) == tmp_path / "data" / "field.parquet"


# Test that a trailing separator or an existing directory wins over the extension
def test_target_directory_with_extension(tmp_path):
    expected = tmp_path / "data.v2" / "field.parquet"
    assert _asset_target_path(f"{tmp_path}/data.v2/", HREF) == expected

    (tmp_path / "data.v2").mkdir()
    assert _asset_target_path(tmp_path / "data.v2", HREF) == expected


# Test that a directory target raises if the URL path names no file
@pytest.mark.parametrize("href", ["https://www.agriatlas.eu/files/", "https://www.agriatlas.eu"])
def test_target_directory_without_filename_raises(tmp_path, href):
    with pytest.raises(AgriAtlasError, match="pass a file path"):
        _asset_target_path(tmp_path, href)


# Test that as_file forces a file or a directory
def test_target_as_file_forced(tmp_path):
    assert _asset_target_path(tmp_path / "data", HREF, as_file=True) == tmp_path / "data"
    assert _asset_target_path(tmp_path / "x.v2", HREF, as_file=False) == (
        tmp_path / "x.v2" / "field.parquet"
    )
