import os

import numpy as np
import pytest

from imgtoolkit import export, io_util
from imgtoolkit.errors import ImgToolkitError


def test_export_basic(gradient, tmp_path):
    out = export.export(gradient, str(tmp_path / "o.png"))
    assert os.path.isfile(out)


def test_export_format_override(gradient, tmp_path):
    out = export.export(gradient, str(tmp_path / "o.png"), fmt="webp")
    assert out.endswith(".webp")
    assert os.path.isfile(out)


def test_export_resize(gradient, tmp_path):
    out = export.export(gradient, str(tmp_path / "o.jpg"), resize=(32, 32),
                        quality=80)
    loaded = io_util.load(out)
    assert max(loaded.shape[:2]) <= 32


@pytest.mark.parametrize("preset", export.list_presets())
def test_all_presets(gradient, tmp_path, preset):
    out = export.export_preset(gradient, str(tmp_path / "img"), preset)
    assert os.path.isfile(out)
    p = export.PRESETS[preset]
    assert out.endswith(p["fmt"])


def test_preset_resizes(gradient, tmp_path):
    out = export.export_preset(gradient, str(tmp_path / "t"), "web-thumb")
    loaded = io_util.load(out)
    assert max(loaded.shape[:2]) <= 400


def test_unknown_preset(gradient, tmp_path):
    with pytest.raises(ImgToolkitError):
        export.export_preset(gradient, str(tmp_path / "x"), "no-such")
