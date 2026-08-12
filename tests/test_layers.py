import numpy as np
import pytest

from imgtoolkit import color
from imgtoolkit.errors import ImgToolkitError
from imgtoolkit.layers import (AdjustmentLayer, Document, ImageLayer, blend)


def solid(h, w, rgb):
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :] = rgb
    return img


# ---- direct blend-mode math (arrays in 0..1) ----

def test_blend_multiply_math():
    cb = np.array([[0.5]], np.float32)
    cs = np.array([[0.4]], np.float32)
    assert np.allclose(blend(cb, cs, "multiply"), 0.2)


def test_blend_screen_math():
    cb = np.array([[0.5]], np.float32)
    cs = np.array([[0.5]], np.float32)
    # 1-(1-.5)(1-.5) = 0.75
    assert np.allclose(blend(cb, cs, "screen"), 0.75)


def test_blend_overlay_math():
    # cb=0.25 <=0.5 -> 2*cb*cs
    assert np.allclose(blend(np.array([0.25]), np.array([0.6]), "overlay"), 0.3)
    # cb=0.75 >0.5 -> 1-2(1-cb)(1-cs)
    val = 1 - 2 * (1 - 0.75) * (1 - 0.6)
    assert np.allclose(blend(np.array([0.75]), np.array([0.6]), "overlay"), val)


def test_blend_darken_lighten_difference_add():
    a = np.array([0.3]); b = np.array([0.7])
    assert np.allclose(blend(a, b, "darken"), 0.3)
    assert np.allclose(blend(a, b, "lighten"), 0.7)
    assert np.allclose(blend(a, b, "difference"), 0.4)
    assert np.allclose(blend(np.array([0.6]), np.array([0.6]), "add"), 1.0)
    assert np.allclose(blend(np.array([0.3]), np.array([0.4]), "add"), 0.7)


def test_blend_unknown_mode():
    with pytest.raises(ImgToolkitError):
        blend(np.array([0.5]), np.array([0.5]), "nope")


# ---- compositing through Document.render ----

def test_multiply_composite():
    doc = Document()
    doc.add_image(solid(8, 8, (200, 100, 50)))
    doc.add_image(solid(8, 8, (100, 100, 100)), blend_mode="multiply")
    out = doc.render()
    expected = np.array([200 * 100 // 255, 100 * 100 // 255, 50 * 100 // 255])
    assert np.all(np.abs(out[0, 0].astype(int) - expected) <= 1)


def test_screen_composite():
    doc = Document()
    doc.add_image(solid(8, 8, (200, 100, 50)))
    doc.add_image(solid(8, 8, (100, 100, 100)), blend_mode="screen")
    out = doc.render()
    for i, (cb, cs) in enumerate([(200, 100), (100, 100), (50, 100)]):
        expected = 255 - (255 - cb) * (255 - cs) / 255.0
        assert abs(int(out[0, 0, i]) - expected) <= 1


def test_normal_opacity_composite():
    doc = Document()
    doc.add_image(solid(8, 8, (200, 100, 40)))
    doc.add_image(solid(8, 8, (0, 200, 240)), opacity=0.5)
    out = doc.render()
    # 50% blend of the two solids
    assert np.all(np.abs(out[0, 0].astype(int) - np.array([100, 150, 140])) <= 1)


def test_normal_full_opacity_covers():
    doc = Document()
    doc.add_image(solid(6, 6, (10, 20, 30)))
    doc.add_image(solid(6, 6, (200, 210, 220)), opacity=1.0)
    out = doc.render()
    assert np.all(out[0, 0] == np.array([200, 210, 220]))


def test_mask_partial():
    doc = Document()
    doc.add_image(solid(4, 4, (0, 0, 0)))
    mask = np.zeros((4, 4), np.uint8)
    mask[:, :2] = 255  # left half only
    doc.add_image(solid(4, 4, (255, 255, 255)), mask=mask)
    out = doc.render()
    assert np.all(out[0, 0] == 255)   # masked-in
    assert np.all(out[0, 3] == 0)     # masked-out


def test_adjustment_layer():
    doc = Document()
    doc.add_image(solid(4, 4, (100, 100, 100)))
    doc.add_adjustment(lambda x: color.brightness(x, 1.5))
    out = doc.render()
    assert np.all(out[0, 0] == 150)


def test_adjustment_opacity():
    doc = Document()
    doc.add_image(solid(4, 4, (100, 100, 100)))
    doc.add_adjustment(lambda x: color.brightness(x, 2.0), opacity=0.5)
    out = doc.render()
    # halfway between 100 and 200
    assert np.all(np.abs(out[0, 0].astype(int) - 150) <= 1)


def test_rgba_output_keep_alpha():
    doc = Document()
    rgba = np.zeros((4, 4, 4), np.uint8)
    rgba[:, :, :3] = 128
    rgba[:, :, 3] = 128  # half transparent
    doc.add_image(rgba)
    out = doc.render(keep_alpha=True)
    assert out.shape[2] == 4
    assert np.all(out[:, :, 3] == 128)


def test_size_mismatch_rejected():
    doc = Document()
    doc.add_image(solid(4, 4, (0, 0, 0)))
    with pytest.raises(ImgToolkitError):
        doc.add_image(solid(5, 5, (0, 0, 0)))


def test_invisible_layer_skipped():
    doc = Document()
    doc.add_image(solid(4, 4, (10, 10, 10)))
    doc.add_image(solid(4, 4, (200, 200, 200)), visible=False)
    out = doc.render()
    assert np.all(out[0, 0] == 10)


def test_layer_reorder():
    doc = Document()
    doc.add_image(solid(4, 4, (10, 10, 10)))
    doc.add_image(solid(4, 4, (200, 200, 200)))
    doc.move_layer(1, 0)  # move white to bottom
    out = doc.render()
    assert np.all(out[0, 0] == 10)  # dark now on top
