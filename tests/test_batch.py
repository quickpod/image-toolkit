import os

import numpy as np
import pytest

from imgtoolkit import batch, io_util
from imgtoolkit.errors import ImgToolkitError


@pytest.fixture
def input_files(gradient, tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"in_{i}.png"
        io_util.save(gradient, str(p))
        paths.append(str(p))
    return paths


def test_batch_resize_count_and_size(input_files, tmp_path):
    out_dir = tmp_path / "out"
    written = batch.batch_resize(input_files, str(out_dir), width=32)
    assert len(written) == 3
    for w in written:
        assert os.path.isfile(w)
        assert io_util.load(w).shape[1] == 32


def test_batch_convert_extensions(input_files, tmp_path):
    out_dir = tmp_path / "webp"
    written = batch.batch_convert(input_files, str(out_dir), "webp")
    assert len(written) == 3
    assert all(w.endswith(".webp") for w in written)


def test_batch_apply_pipeline(input_files, tmp_path):
    ops = [("grayscale", {}), ("brightness", {"factor": 1.2})]
    written = batch.batch_apply(input_files, str(tmp_path / "p"), ops)
    assert len(written) == 3
    img = io_util.load(written[0])
    assert np.array_equal(img[:, :, 0], img[:, :, 1])  # grayscale applied


def test_batch_naming_deterministic(input_files, tmp_path):
    written = batch.batch_apply(input_files, str(tmp_path / "n"), [],
                                naming="frame_{index:03d}{ext}")
    names = sorted(os.path.basename(w) for w in written)
    assert names == ["frame_000.png", "frame_001.png", "frame_002.png"]


def test_batch_watermark(input_files, tmp_path):
    written = batch.batch_watermark(input_files, str(tmp_path / "wm"),
                                    text="(c)", out_format="png")
    assert len(written) == 3


def test_batch_strip_metadata(input_files, tmp_path):
    written = batch.batch_strip_metadata(input_files, str(tmp_path / "s"))
    assert len(written) == 3
    assert all(os.path.isfile(w) for w in written)


def test_batch_rename(input_files, tmp_path):
    written = batch.batch_rename(input_files, str(tmp_path / "r"),
                                 pattern="pic_{index}{ext}", start=10)
    names = [os.path.basename(w) for w in written]
    assert names == ["pic_10.png", "pic_11.png", "pic_12.png"]


def test_batch_unknown_op(input_files, tmp_path):
    with pytest.raises(ImgToolkitError):
        batch.batch_apply(input_files, str(tmp_path / "x"), [("nope", {})])
