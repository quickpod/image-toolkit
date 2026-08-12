import numpy as np
import pytest

from imgtoolkit import retouch
from imgtoolkit.errors import ImgToolkitError


def test_inpaint_fills_masked_region(gradient):
    img = gradient.copy()
    # corrupt a block
    img[20:35, 30:50] = 0
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[20:35, 30:50] = 255
    out = retouch.object_removal(img, mask)
    # masked region should change (be filled), no longer all-black
    assert out[20:35, 30:50].mean() > 10
    # unmasked region essentially unchanged
    unmasked = np.ones(img.shape[:2], bool)
    unmasked[15:40, 25:55] = False  # allow a border of bleed around the hole
    assert np.array_equal(out[unmasked], img[unmasked])


def test_heal_point(gradient):
    out = retouch.heal(gradient, point=(48, 32), radius=8)
    assert out.shape == gradient.shape


def test_heal_needs_mask_or_point(gradient):
    with pytest.raises(ImgToolkitError):
        retouch.heal(gradient)


def test_spot_removal(gradient):
    out = retouch.spot_removal(gradient, (40, 20), radius=6)
    assert out.shape == gradient.shape


def test_clone_stamp_copies(gradient):
    out = retouch.clone_stamp(gradient, src=(20, 20), dst=(70, 40), radius=6)
    assert out.shape == gradient.shape
    # destination area should have changed toward the source content
    assert not np.array_equal(out[34:46, 64:76], gradient[34:46, 64:76])


def test_red_eye_removal_reduces_red():
    img = np.zeros((40, 40, 3), np.uint8)
    img[10:30, 10:30] = [220, 20, 20]  # a red "eye"
    out = retouch.red_eye_removal(img, (5, 5, 35, 35))
    assert out[10:30, 10:30, 0].mean() < 220


def test_skin_smooth(gradient):
    out = retouch.skin_smooth(gradient, 0.6)
    assert out.shape == gradient.shape


def test_denoise_reduces_noise_variance(noisy, gradient):
    out = retouch.denoise(noisy, 12.0)
    # residual noise vs clean signal should shrink
    before = (noisy.astype(float) - gradient.astype(float)).std()
    after = (out.astype(float) - gradient.astype(float)).std()
    assert after < before


def test_reduce_noise_levels(noisy):
    out = retouch.reduce_noise(noisy, "high")
    assert out.std() < noisy.std()
    with pytest.raises(ImgToolkitError):
        retouch.reduce_noise(noisy, "extreme")


def test_inpaint_preserves_alpha(rgba):
    mask = np.zeros(rgba.shape[:2], np.uint8)
    mask[10:20, 10:20] = 255
    out = retouch.object_removal(rgba, mask)
    assert out.shape[2] == 4
