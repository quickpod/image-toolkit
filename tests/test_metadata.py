import numpy as np
import pytest

from imgtoolkit import io_util, metadata
from imgtoolkit.errors import ImgToolkitError


def test_set_read_strip_roundtrip(gradient, tmp_path):
    src = tmp_path / "src.jpg"
    io_util.save(gradient, str(src), quality=95)

    tagged = tmp_path / "tagged.jpg"
    metadata.set_exif(str(src), str(tagged),
                      {"Artist": "Ansel", "Copyright": "CC-BY"})
    data = metadata.read_exif(str(tagged))
    assert any("Ansel" in str(v) for v in data.values())

    stripped = tmp_path / "clean.jpg"
    metadata.strip_metadata(str(tagged), str(stripped))
    after = metadata.read_exif(str(stripped))
    # No Artist/Copyright fields survive.
    assert not any("Ansel" in str(v) for v in after.values())


def test_read_exif_none(gradient, tmp_path):
    p = tmp_path / "plain.png"
    io_util.save(gradient, str(p))
    data = metadata.read_exif(str(p))
    assert isinstance(data, dict)


def test_set_exif_rejects_png(gradient, tmp_path):
    src = tmp_path / "s.png"
    io_util.save(gradient, str(src))
    with pytest.raises(ImgToolkitError):
        metadata.set_exif(str(src), str(tmp_path / "o.png"), {"Artist": "x"})


def test_set_exif_unknown_field(gradient, tmp_path):
    src = tmp_path / "s.jpg"
    io_util.save(gradient, str(src))
    with pytest.raises(ImgToolkitError):
        metadata.set_exif(str(src), str(tmp_path / "o.jpg"), {"Nope": "x"})


def test_strip_missing_file(tmp_path):
    with pytest.raises(ImgToolkitError):
        metadata.strip_metadata(str(tmp_path / "missing.jpg"),
                                str(tmp_path / "o.jpg"))
