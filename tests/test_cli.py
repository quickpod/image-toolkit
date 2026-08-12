import os

import numpy as np
import pytest

from imgtoolkit import io_util
from imgtoolkit.__main__ import main


@pytest.fixture
def img_file(gradient, tmp_path):
    p = tmp_path / "in.png"
    io_util.save(gradient, str(p))
    return str(p)


def test_cli_resize(img_file, tmp_path):
    out = str(tmp_path / "out.png")
    assert main(["resize", img_file, out, "--width", "40"]) == 0
    assert io_util.load(out).shape[1] == 40


def test_cli_filter(img_file, tmp_path):
    out = str(tmp_path / "f.png")
    assert main(["filter", img_file, out, "gaussian", "--radius", "2"]) == 0
    assert os.path.isfile(out)


def test_cli_watermark(img_file, tmp_path):
    out = str(tmp_path / "w.png")
    assert main(["watermark", img_file, out, "--text", "hi"]) == 0
    assert os.path.isfile(out)


def test_cli_inpaint(img_file, tmp_path):
    mask = np.zeros((64, 96), np.uint8)
    mask[20:30, 20:40] = 255
    mp = str(tmp_path / "mask.png")
    io_util.save(mask, mp)
    out = str(tmp_path / "ip.png")
    assert main(["inpaint", img_file, out, "--mask", mp]) == 0
    assert os.path.isfile(out)


def test_cli_convert(img_file, tmp_path):
    out = str(tmp_path / "c.webp")
    assert main(["convert", img_file, out]) == 0
    assert os.path.isfile(out)


def test_cli_autoenhance(img_file, tmp_path):
    out = str(tmp_path / "ae.jpg")
    assert main(["autoenhance", img_file, out, "--quality", "85"]) == 0


def test_cli_batch_resize(img_file, tmp_path):
    out_dir = str(tmp_path / "b")
    rc = main(["batch", "resize", img_file, "--out-dir", out_dir,
               "--width", "20"])
    assert rc == 0
    assert len(os.listdir(out_dir)) == 1


def test_cli_error_clean_exit(tmp_path, capsys):
    rc = main(["resize", "/no/such.png", str(tmp_path / "o.png"),
               "--width", "10"])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("error:")


def test_cli_content_aware_scale(img_file, tmp_path):
    out = str(tmp_path / "cas.png")
    rc = main(["content-aware-scale", img_file, out, "--width", "80"])
    assert rc == 0
    assert io_util.load(out).shape[1] == 80


def test_cli_exif(img_file, capsys):
    rc = main(["exif", img_file])
    assert rc == 0
