import numpy as np
import pytest

from imgtoolkit import color


def test_brightness_increases_mean(gradient):
    out = color.brightness(gradient, 1.4)
    assert out.mean() > gradient.mean()
    darker = color.brightness(gradient, 0.6)
    assert darker.mean() < gradient.mean()


def test_contrast_spreads(gradient):
    out = color.contrast(gradient, 1.6)
    assert out.std() > gradient.std()


def test_exposure(gradient):
    up = color.exposure(gradient, 1.0)
    assert up.mean() > gradient.mean()


def test_saturation_zero_is_gray(gradient):
    out = color.saturation(gradient, 0.0)
    # channels approximately equal when desaturated
    diff = np.abs(out[:, :, 0].astype(int) - out[:, :, 1].astype(int))
    assert diff.mean() < 3


def test_grayscale_channels_equal(gradient):
    out = color.grayscale(gradient, keep_channels=True)
    assert np.array_equal(out[:, :, 0], out[:, :, 1])
    assert np.array_equal(out[:, :, 1], out[:, :, 2])


def test_grayscale_single_channel(gradient):
    out = color.grayscale(gradient, keep_channels=False)
    assert out.ndim == 2


def test_invert(gradient):
    out = color.invert(gradient)
    assert np.array_equal(out, 255 - gradient)
    assert np.array_equal(color.invert(out), gradient)


def test_invert_preserves_alpha(rgba):
    out = color.invert(rgba)
    assert np.array_equal(out[:, :, 3], rgba[:, :, 3])


def test_sepia_warm(gradient):
    out = color.sepia(gradient, 1.0)
    # sepia => red channel tends to exceed blue
    assert out[:, :, 0].mean() > out[:, :, 2].mean()


def test_hue_shift_360_identity(gradient):
    out = color.hue_shift(gradient, 360.0)
    assert np.abs(out.astype(int) - gradient.astype(int)).mean() < 3


def test_levels_black_white_point():
    ramp = np.tile(np.arange(256, dtype=np.uint8), (4, 1))
    img = np.dstack([ramp, ramp, ramp])
    out = color.levels(img, in_black=64, in_white=192, gamma=1.0)
    assert out.min() == 0
    assert out.max() == 255
    # midpoint stays roughly mid
    assert 100 < int(out[0, 128, 0]) < 160


def test_levels_gamma_brightens():
    ramp = np.tile(np.arange(256, dtype=np.uint8), (4, 1))
    img = np.dstack([ramp, ramp, ramp])
    bright = color.levels(img, gamma=2.0)
    assert bright.mean() > img.mean()


def test_curves_identity(gradient):
    out = color.curves(gradient, "rgb", [(0, 0), (255, 255)])
    assert np.array_equal(out, gradient)


def test_curves_invert(gradient):
    out = color.curves(gradient, "rgb", [(0, 255), (255, 0)])
    assert np.array_equal(out, 255 - gradient)


def test_curves_single_channel(gradient):
    out = color.curves(gradient, "r", [(0, 0), (255, 128)])
    # red channel dimmed, green unchanged
    assert out[:, :, 0].max() <= 129
    assert np.array_equal(out[:, :, 1], gradient[:, :, 1])


def test_white_balance_auto_neutralizes():
    # strong blue cast
    img = np.zeros((10, 10, 3), np.uint8)
    img[:, :, 0] = 100
    img[:, :, 1] = 100
    img[:, :, 2] = 200
    out = color.white_balance(img, auto=True)
    means = out.reshape(-1, 3).mean(axis=0)
    assert np.ptp(means) < np.ptp([100, 100, 200])


def test_auto_enhance_runs(gradient):
    out = color.auto_enhance(gradient)
    assert out.shape == gradient.shape
    assert out.dtype == np.uint8


def test_color_balance_shifts(gradient):
    out = color.color_balance(gradient, highlights=(30, 0, 0))
    assert out[:, :, 0].mean() >= gradient[:, :, 0].mean()


def test_vibrance(gradient):
    out = color.vibrance(gradient, 0.5)
    assert out.shape == gradient.shape
