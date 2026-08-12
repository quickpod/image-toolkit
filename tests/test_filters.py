import numpy as np
import pytest

from imgtoolkit import filters
from imgtoolkit.errors import ImgToolkitError


def _changed(a, b):
    return not np.array_equal(a, b)


def test_gaussian_blur_reduces_variance(noisy):
    out = filters.gaussian_blur(noisy, 3.0)
    assert out.shape == noisy.shape
    assert out.std() < noisy.std()


def test_motion_blur_runs(gradient):
    out = filters.motion_blur(gradient, angle=30, distance=11)
    assert _changed(out, gradient)


def test_lens_blur_runs(gradient):
    out = filters.lens_blur(gradient, radius=5)
    assert _changed(out, gradient)


def test_sharpen_increases_edges(gradient):
    blurred = filters.gaussian_blur(gradient, 2.0)
    sharp = filters.sharpen(blurred, amount=1.5)
    # sharpening should raise local contrast vs blurred
    assert sharp.std() >= blurred.std()


def test_vignette_darkens_corners(gradient):
    out = filters.vignette(gradient, strength=0.8)
    # a corner should be darker than the centre after vignetting
    h, w = gradient.shape[:2]
    corner = out[0:3, 0:3].mean()
    center = out[h // 2 - 2:h // 2 + 2, w // 2 - 2:w // 2 + 2].mean()
    assert corner < center


def test_vintage_deterministic(gradient):
    a = filters.vintage(gradient, seed=123)
    b = filters.vintage(gradient, seed=123)
    assert np.array_equal(a, b)
    c = filters.vintage(gradient, seed=999)
    assert _changed(a, c)


def test_pencil_sketch(gradient):
    out = filters.pencil_sketch(gradient)
    assert out.shape[:2] == gradient.shape[:2]


def test_stylize(gradient):
    out = filters.stylize(gradient)
    assert out.shape[:2] == gradient.shape[:2]


def test_hdr_effect(gradient):
    out = filters.hdr_effect(gradient, 0.6)
    assert out.shape[:2] == gradient.shape[:2]


def test_cartoon(gradient):
    out = filters.cartoon(gradient)
    assert out.shape[:2] == gradient.shape[:2]


def test_oil_paint(gradient):
    out = filters.oil_paint(gradient)
    assert out.shape[:2] == gradient.shape[:2]


def _write_identity_cube(path, size=2):
    lines = [f"LUT_3D_SIZE {size}"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                rr = r / (size - 1)
                gg = g / (size - 1)
                bb = b / (size - 1)
                lines.append(f"{rr:.6f} {gg:.6f} {bb:.6f}")
    path.write_text("\n".join(lines))


def _write_invert_cube(path, size=2):
    lines = [f"LUT_3D_SIZE {size}"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                rr = 1 - r / (size - 1)
                gg = 1 - g / (size - 1)
                bb = 1 - b / (size - 1)
                lines.append(f"{rr:.6f} {gg:.6f} {bb:.6f}")
    path.write_text("\n".join(lines))


def test_apply_lut_identity(gradient, tmp_path):
    cube = tmp_path / "id.cube"
    _write_identity_cube(cube)
    out = filters.apply_lut(gradient, str(cube))
    assert np.abs(out.astype(int) - gradient.astype(int)).max() <= 1


def test_apply_lut_invert(gradient, tmp_path):
    cube = tmp_path / "inv.cube"
    _write_invert_cube(cube)
    out = filters.apply_lut(gradient, str(cube))
    assert np.abs(out.astype(int) - (255 - gradient).astype(int)).max() <= 2


def test_parse_cube_bad(tmp_path):
    bad = tmp_path / "bad.cube"
    bad.write_text("TITLE nope\n0.1 0.2 0.3\n")
    with pytest.raises(ImgToolkitError):
        filters.parse_cube_lut(str(bad))


def test_apply_lut_preserves_alpha(rgba, tmp_path):
    cube = tmp_path / "id.cube"
    _write_identity_cube(cube)
    out = filters.apply_lut(rgba, str(cube))
    assert out.shape[2] == 4
    assert np.array_equal(out[:, :, 3], rgba[:, :, 3])
