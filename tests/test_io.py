import numpy as np
import pytest

from imgtoolkit import io_util
from imgtoolkit.errors import ImgToolkitError


@pytest.mark.parametrize("ext", [".png", ".jpg", ".webp", ".tif", ".bmp"])
def test_roundtrip_rgb(gradient, tmp_path, ext):
    p = tmp_path / ("img" + ext)
    io_util.save(gradient, str(p), quality=95)
    loaded = io_util.load(str(p))
    assert loaded.shape[:2] == gradient.shape[:2]
    assert loaded.ndim == 3 and loaded.shape[2] in (3, 4)
    if ext in (".png", ".tif", ".bmp"):
        # lossless: exact match
        assert np.array_equal(loaded[:, :, :3], gradient)


def test_roundtrip_alpha_png(rgba, tmp_path):
    p = tmp_path / "a.png"
    io_util.save(rgba, str(p))
    loaded = io_util.load(str(p))
    assert loaded.shape[2] == 4
    assert np.array_equal(loaded, rgba)


def test_roundtrip_alpha_webp(rgba, tmp_path):
    p = tmp_path / "a.webp"
    io_util.save(rgba, str(p), quality=100)
    loaded = io_util.load(str(p))
    assert loaded.shape[2] == 4  # alpha preserved through WebP


def test_missing_file():
    with pytest.raises(ImgToolkitError):
        io_util.load("/no/such/file.png")


def test_save_raw_rejected(gradient, tmp_path):
    with pytest.raises(ImgToolkitError):
        io_util.save(gradient, str(tmp_path / "x.cr2"))


def test_is_raw_path():
    assert io_util.is_raw_path("a.CR2")
    assert io_util.is_raw_path("b.nef")
    assert not io_util.is_raw_path("c.png")


def test_raw_load_guarded(tmp_path):
    """RAW loading either works (rawpy present) or raises cleanly (absent)."""
    fake = tmp_path / "fake.dng"
    fake.write_bytes(b"not a real raw")
    with pytest.raises(ImgToolkitError):
        io_util.load(str(fake))


def test_image_info(gradient, tmp_path):
    p = tmp_path / "i.png"
    io_util.save(gradient, str(p))
    info = io_util.image_info(str(p))
    assert info["width"] == gradient.shape[1]
    assert info["height"] == gradient.shape[0]
