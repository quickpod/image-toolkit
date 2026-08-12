import numpy as np
import pytest

from imgtoolkit import annotate, io_util, watermark


def base():
    return np.full((60, 90, 3), 128, np.uint8)


def test_draw_rect_adds_content():
    img = base()
    out = annotate.draw_rect(img, (10, 10, 40, 40), color=(255, 0, 0), width=2)
    assert out.shape[2] == 4
    assert not np.array_equal(out[:, :, :3], img)


def test_draw_ellipse():
    out = annotate.draw_ellipse(base(), (5, 5, 50, 40))
    assert out.shape[2] == 4


def test_draw_line_and_arrow():
    out = annotate.draw_line(base(), (0, 0), (80, 50))
    assert not np.array_equal(out[:, :, :3], base())
    out2 = annotate.draw_arrow(base(), (5, 5), (70, 40))
    assert not np.array_equal(out2[:, :, :3], base())


def test_add_text():
    out = annotate.add_text(base(), "Hi", (10, 10), font_size=20,
                            color=(255, 255, 0))
    assert not np.array_equal(out[:, :, :3], base())


def test_brush_and_highlighter():
    pts = [(5, 5), (20, 30), (60, 10)]
    out = annotate.brush_stroke(base(), pts, width=6, color=(0, 0, 0))
    assert not np.array_equal(out[:, :, :3], base())
    hl = annotate.highlighter(base(), pts, width=10, alpha=120)
    assert not np.array_equal(hl[:, :, :3], base())


def test_text_watermark_adds_content():
    img = base()
    out = watermark.text_watermark(img, "(c) me", opacity=0.8,
                                   position="bottom-right", size=18)
    assert out.shape[2] == 4
    assert not np.array_equal(out[:, :, :3], img)


def test_text_watermark_positions():
    for pos in ["top-left", "center", "bottom-right", "top", "left"]:
        out = watermark.text_watermark(base(), "x", position=pos, size=14)
        assert out.shape[:2] == (60, 90)


def test_image_watermark(tmp_path):
    mark = np.zeros((20, 20, 4), np.uint8)
    mark[:, :, 0] = 255
    mark[:, :, 3] = 255
    mp = tmp_path / "mark.png"
    io_util.save(mark, str(mp))
    out = watermark.image_watermark(base(), str(mp), opacity=0.7, scale=0.3)
    assert out.shape[2] == 4
    assert not np.array_equal(out[:, :, :3], base())


def test_text_watermark_rotation():
    out = watermark.text_watermark(base(), "diag", rotation=45, size=16)
    assert out.shape[:2] == (60, 90)
