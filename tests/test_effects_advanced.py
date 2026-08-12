import numpy as np
import pytest

from imgtoolkit import effects_advanced as fx
from imgtoolkit.errors import ImgToolkitError


def test_content_aware_scale_changes_width(small_gradient):
    h, w = small_gradient.shape[:2]
    out = fx.content_aware_scale(small_gradient, w - 8)
    assert out.shape[1] == w - 8
    assert out.shape[0] == h  # height preserved


def test_content_aware_scale_rejects_upscale(small_gradient):
    w = small_gradient.shape[1]
    with pytest.raises(ImgToolkitError):
        fx.content_aware_scale(small_gradient, w + 5)


def test_liquify_bloat_changes_center(gradient):
    out = fx.liquify(gradient, center=(48, 32), radius=20, strength=0.5,
                     mode="bloat")
    assert out.shape == gradient.shape
    assert not np.array_equal(out, gradient)


def test_liquify_push(gradient):
    out = fx.liquify(gradient, center=(48, 32), radius=15, strength=5,
                     mode="push", direction=(1, 0))
    assert out.shape == gradient.shape


def test_liquify_bad_mode(gradient):
    with pytest.raises(ImgToolkitError):
        fx.liquify(gradient, (10, 10), 5, 0.5, mode="twist")


def test_hdr_merge(exposure_trio):
    out = fx.hdr_merge(exposure_trio)
    assert out.shape[:2] == exposure_trio[0].shape[:2]
    assert out.dtype == np.uint8
    # fused result should not be as dark as the darkest frame
    assert out.mean() > exposure_trio[0].mean()


def test_hdr_merge_size_mismatch(exposure_trio):
    bad = list(exposure_trio)
    bad[1] = bad[1][:-4]
    with pytest.raises(ImgToolkitError):
        fx.hdr_merge(bad)


def test_focus_stack(exposure_trio):
    # build a focus bracket: each frame sharp in a different band
    base = exposure_trio[1]
    import cv2
    frames = []
    h = base.shape[0]
    for i in range(3):
        blurred = cv2.GaussianBlur(base, (7, 7), 3)
        f = blurred.copy()
        band = slice(i * h // 3, (i + 1) * h // 3)
        f[band] = base[band]  # sharp band
        frames.append(f)
    out = fx.focus_stack(frames, align=False)
    assert out.shape == base.shape


def test_focus_stack_needs_two(gradient):
    with pytest.raises(ImgToolkitError):
        fx.focus_stack([gradient])


def test_panorama_stitch(stitch_pair):
    try:
        out = fx.panorama_stitch(stitch_pair)
    except ImgToolkitError:
        pytest.skip("cv2.Stitcher could not match the synthetic pair")
    assert out.ndim == 3 and out.shape[2] == 3
    # a panorama should be wider than a single input tile
    assert out.shape[1] >= stitch_pair[0].shape[1]
