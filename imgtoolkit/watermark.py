"""Text and image watermarking (Pillow-based, alpha-aware)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ._util import ensure_ndarray
from .annotate import _load_font, _norm_color, _to_rgba_pil
from .errors import ImgToolkitError

_POSITIONS = {
    "top-left", "top", "top-right",
    "left", "center", "centre", "right",
    "bottom-left", "bottom", "bottom-right",
}


def _anchor_xy(pos, canvas_wh, item_wh, margin):
    cw, ch = canvas_wh
    iw, ih = item_wh
    pos = pos.lower()
    if pos not in _POSITIONS:
        raise ImgToolkitError(f"position must be one of {sorted(_POSITIONS)}")
    if "left" in pos:
        x = margin
    elif "right" in pos:
        x = cw - iw - margin
    else:
        x = (cw - iw) // 2
    if "top" in pos:
        y = margin
    elif "bottom" in pos:
        y = ch - ih - margin
    else:
        y = (ch - ih) // 2
    return int(x), int(y)


def text_watermark(img, text, opacity=0.5, position="bottom-right",
                   rotation=0.0, size=32, color=(255, 255, 255),
                   margin=16, font_path=None) -> np.ndarray:
    """Stamp ``text`` as a watermark.

    ``opacity`` in [0, 1], ``position`` a named anchor (e.g. 'bottom-right',
    'center'), ``rotation`` degrees CCW, ``size`` font px, ``color`` RGB.
    Returns an RGBA ndarray.
    """
    base = _to_rgba_pil(img)
    font = _load_font(size, font_path)

    # Measure text.
    tmp = Image.new("RGBA", (1, 1))
    dtmp = ImageDraw.Draw(tmp)
    bbox = dtmp.textbbox((0, 0), str(text), font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(4, size // 8)

    # Render text onto its own tight tile, then rotate.
    tile = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    dt = ImageDraw.Draw(tile)
    a = int(np.clip(opacity, 0, 1) * 255)
    col = _norm_color(color)[:3] + (a,)
    dt.text((pad - bbox[0], pad - bbox[1]), str(text), font=font, fill=col)
    if rotation:
        tile = tile.rotate(rotation, expand=True, resample=Image.BICUBIC)

    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    x, y = _anchor_xy(position, base.size, tile.size, margin)
    ov.alpha_composite(tile, (x, y))
    out = Image.alpha_composite(base, ov)
    return np.asarray(out, dtype=np.uint8)


def image_watermark(img, overlay_path, opacity=0.5, position="bottom-right",
                    scale=0.2, margin=16) -> np.ndarray:
    """Composite a watermark image loaded from ``overlay_path``.

    ``scale`` sizes the overlay relative to the base width; ``opacity`` in
    [0, 1] modulates its alpha. Returns an RGBA ndarray.
    """
    ensure_ndarray(img)
    base = _to_rgba_pil(img)
    try:
        mark = Image.open(overlay_path).convert("RGBA")
    except Exception as exc:
        raise ImgToolkitError(f"Could not load watermark {overlay_path}: {exc}")

    target_w = max(1, int(base.width * scale))
    ratio = target_w / mark.width
    target_h = max(1, int(mark.height * ratio))
    mark = mark.resize((target_w, target_h), Image.LANCZOS)

    # Apply opacity by scaling the alpha channel.
    if opacity < 1.0:
        r, g, b, alpha = mark.split()
        alpha = alpha.point(lambda v: int(v * np.clip(opacity, 0, 1)))
        mark = Image.merge("RGBA", (r, g, b, alpha))

    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    x, y = _anchor_xy(position, base.size, mark.size, margin)
    ov.alpha_composite(mark, (x, y))
    out = Image.alpha_composite(base, ov)
    return np.asarray(out, dtype=np.uint8)
