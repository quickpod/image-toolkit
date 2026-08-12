"""Annotation primitives drawn with Pillow ``ImageDraw`` on RGBA overlays.

Every function returns a new RGBA ndarray with the annotation composited over
the input. Shapes/text are drawn on a transparent overlay first so partial
opacity works correctly. Colours are RGBA tuples (alpha optional, defaults to
opaque).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ._util import ensure_ndarray
from .errors import ImgToolkitError


def _to_rgba_pil(img: np.ndarray) -> Image.Image:
    ensure_ndarray(img)
    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return Image.fromarray(img.astype(np.uint8))  # inferred "RGBA"


def _norm_color(color, default_alpha=255):
    if isinstance(color, (int, float)):
        c = (int(color),) * 3
    else:
        c = tuple(int(v) for v in color)
    if len(c) == 3:
        c = c + (default_alpha,)
    return c


def _finish(base: Image.Image, overlay: Image.Image) -> np.ndarray:
    out = Image.alpha_composite(base, overlay)
    return np.asarray(out, dtype=np.uint8)


def _new_overlay(base):
    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    return ov, ImageDraw.Draw(ov)


def draw_rect(img, box, color=(255, 0, 0), width=3, fill=None) -> np.ndarray:
    """Draw a rectangle. ``box`` = (left, top, right, bottom)."""
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    d.rectangle([int(v) for v in box], outline=_norm_color(color), width=int(width),
                fill=_norm_color(fill) if fill is not None else None)
    return _finish(base, ov)


def draw_ellipse(img, box, color=(255, 0, 0), width=3, fill=None) -> np.ndarray:
    """Draw an ellipse bounded by ``box`` = (left, top, right, bottom)."""
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    d.ellipse([int(v) for v in box], outline=_norm_color(color), width=int(width),
              fill=_norm_color(fill) if fill is not None else None)
    return _finish(base, ov)


def draw_line(img, start, end, color=(255, 0, 0), width=3) -> np.ndarray:
    """Draw a line from ``start`` to ``end`` (each an (x, y) point)."""
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    d.line([tuple(start), tuple(end)], fill=_norm_color(color), width=int(width))
    return _finish(base, ov)


def draw_arrow(img, start, end, color=(255, 0, 0), width=3,
               head_size=None) -> np.ndarray:
    """Draw an arrow from ``start`` to ``end`` with a solid head at ``end``."""
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    col = _norm_color(color)
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    d.line([(x0, y0), (x1, y1)], fill=col, width=int(width))
    ang = np.arctan2(y1 - y0, x1 - x0)
    hs = float(head_size) if head_size else max(10.0, width * 4.0)
    for sign in (+1, -1):
        a = ang + sign * np.radians(150)
        hx = x1 + hs * np.cos(a)
        hy = y1 + hs * np.sin(a)
        d.line([(x1, y1), (hx, hy)], fill=col, width=int(width))
    return _finish(base, ov)


def _load_font(font_size, font_path=None):
    if font_path:
        try:
            return ImageFont.truetype(font_path, int(font_size))
        except Exception as exc:
            raise ImgToolkitError(f"Could not load font {font_path}: {exc}")
    # Try a common truetype; fall back to the bitmap default (scales poorly
    # but always available in a headless environment).
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, int(font_size))
        except Exception:
            continue
    return ImageFont.load_default()


def add_text(img, text, xy, font_size=24, color=(255, 255, 255),
             font_path=None, anchor="la", stroke_width=0,
             stroke_color=(0, 0, 0)) -> np.ndarray:
    """Draw ``text`` at ``xy``.

    ``font_size`` in px, ``color`` RGB(A). Optionally supply ``font_path`` to
    a TTF; otherwise DejaVuSans / a bitmap fallback is used. ``stroke_width``
    adds an outline for legibility.
    """
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    font = _load_font(font_size, font_path)
    d.text(tuple(xy), str(text), fill=_norm_color(color), font=font,
           anchor=anchor, stroke_width=int(stroke_width),
           stroke_fill=_norm_color(stroke_color))
    return _finish(base, ov)


def brush_stroke(img, points, width=8, color=(0, 0, 0)) -> np.ndarray:
    """Freehand brush: a rounded polyline through ``points`` = [(x, y), ...]."""
    if len(points) < 1:
        raise ImgToolkitError("brush_stroke needs at least one point")
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    col = _norm_color(color)
    pts = [tuple(p) for p in points]
    if len(pts) == 1:
        r = width / 2.0
        x, y = pts[0]
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    else:
        d.line(pts, fill=col, width=int(width), joint="curve")
        r = width / 2.0
        for x, y in pts:
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    return _finish(base, ov)


def highlighter(img, points, width=16, color=(255, 255, 0), alpha=100) -> np.ndarray:
    """Semi-transparent highlighter stroke through ``points``.

    ``alpha`` in 0..255 sets the translucency of the highlight.
    """
    if len(points) < 1:
        raise ImgToolkitError("highlighter needs at least one point")
    base = _to_rgba_pil(img)
    ov, d = _new_overlay(base)
    col = _norm_color(color, default_alpha=int(alpha))
    col = (col[0], col[1], col[2], int(alpha))
    pts = [tuple(p) for p in points]
    if len(pts) == 1:
        r = width / 2.0
        x, y = pts[0]
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    else:
        d.line(pts, fill=col, width=int(width), joint="curve")
    return _finish(base, ov)
