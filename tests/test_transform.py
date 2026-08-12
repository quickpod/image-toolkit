import numpy as np
import pytest

from imgtoolkit import transform
from imgtoolkit.errors import ImgToolkitError


def test_crop(gradient):
    out = transform.crop(gradient, (10, 5, 40, 30))
    assert out.shape[:2] == (25, 30)


def test_crop_invalid(gradient):
    with pytest.raises(ImgToolkitError):
        transform.crop(gradient, (0, 0, 1000, 5))


def test_rotate_expand(gradient):
    out = transform.rotate(gradient, 90, expand=True)
    h, w = gradient.shape[:2]
    assert out.shape[0] == w and out.shape[1] == h


def test_rotate_no_expand(gradient):
    out = transform.rotate(gradient, 45, expand=False)
    assert out.shape[:2] == gradient.shape[:2]


def test_rotate_alpha_preserved(rgba):
    out = transform.rotate(rgba, 30, expand=True)
    assert out.shape[2] == 4


def test_flip_h(gradient):
    out = transform.flip(gradient, "h")
    assert np.array_equal(out, gradient[:, ::-1])


def test_flip_v(gradient):
    out = transform.flip(gradient, "v")
    assert np.array_equal(out, gradient[::-1, :])


def test_resize_exact():
    img = np.zeros((50, 100, 3), np.uint8)
    out = transform.resize(img, 40, 40, keep_aspect=False)
    assert out.shape[:2] == (40, 40)


def test_resize_keep_aspect_width(gradient):
    h, w = gradient.shape[:2]
    out = transform.resize(gradient, width=w // 2)
    assert out.shape[1] == w // 2
    assert abs(out.shape[0] - h // 2) <= 1


def test_canvas_resize_pad(gradient):
    out = transform.canvas_resize(gradient, 200, 200, anchor="center")
    assert out.shape[:2] == (200, 200)


def test_canvas_resize_crop(gradient):
    out = transform.canvas_resize(gradient, 20, 20, anchor="top-left")
    assert out.shape[:2] == (20, 20)
    assert np.array_equal(out[:, :, :3], gradient[:20, :20, :3])


def test_perspective_correct(gradient):
    h, w = gradient.shape[:2]
    quad = [(5, 5), (w - 10, 2), (w - 3, h - 6), (8, h - 3)]
    out = transform.perspective_correct(gradient, quad, out_size=(50, 40))
    assert out.shape[:2] == (40, 50)


def test_straighten(gradient):
    out = transform.straighten(gradient, 3.0)
    assert out.shape[:2] == gradient.shape[:2]
