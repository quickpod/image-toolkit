"""Geometric transforms: crop, rotate, flip, resize, canvas, perspective.

All functions take and return RGB/RGBA ``uint8`` ndarrays and preserve the
alpha channel where present.
"""

from __future__ import annotations

import cv2
import numpy as np

from ._util import ensure_ndarray, has_alpha, to_uint8
from .errors import ImgToolkitError

# Resample name -> cv2 interpolation flag.
_RESAMPLE = {
    "nearest": cv2.INTER_NEAREST,
    "bilinear": cv2.INTER_LINEAR,
    "linear": cv2.INTER_LINEAR,
    "bicubic": cv2.INTER_CUBIC,
    "cubic": cv2.INTER_CUBIC,
    "area": cv2.INTER_AREA,
    "lanczos": cv2.INTER_LANCZOS4,
}


def _interp(name: str, shrinking: bool):
    if name == "auto":
        return cv2.INTER_AREA if shrinking else cv2.INTER_CUBIC
    try:
        return _RESAMPLE[name]
    except KeyError:
        raise ImgToolkitError(
            f"Unknown resample '{name}'. Choose from {sorted(_RESAMPLE)} or 'auto'."
        )


def crop(img: np.ndarray, box) -> np.ndarray:
    """Crop to ``box`` = ``(left, top, right, bottom)`` in pixel coords.

    ``right``/``bottom`` are exclusive. Raises if the box is empty or lies
    outside the image.
    """
    img = ensure_ndarray(img)
    h, w = img.shape[:2]
    try:
        left, top, right, bottom = [int(round(v)) for v in box]
    except Exception:
        raise ImgToolkitError("crop box must be (left, top, right, bottom)")
    if not (0 <= left < right <= w and 0 <= top < bottom <= h):
        raise ImgToolkitError(
            f"crop box {box} is invalid for image of size {w}x{h}"
        )
    return np.ascontiguousarray(img[top:bottom, left:right])


def rotate(img: np.ndarray, deg: float, expand: bool = True,
           fill=(0, 0, 0, 0)) -> np.ndarray:
    """Rotate ``deg`` degrees counter-clockwise about the centre.

    When ``expand`` is True the output canvas grows to contain the whole
    rotated image; otherwise it keeps the original size. Transparent fill is
    used for RGBA, black for RGB (override with ``fill``).
    """
    img = ensure_ndarray(img)
    h, w = img.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    M = cv2.getRotationMatrix2D((cx, cy), deg, 1.0)
    if expand:
        cos, sin = abs(M[0, 0]), abs(M[0, 1])
        nw = int(round(h * sin + w * cos))
        nh = int(round(h * cos + w * sin))
        M[0, 2] += (nw - w) / 2.0
        M[1, 2] += (nh - h) / 2.0
        out_size = (nw, nh)
    else:
        out_size = (w, h)
    border = fill[:img.shape[2]] if img.ndim == 3 else fill[0]
    out = cv2.warpAffine(
        img, M, out_size, flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=border,
    )
    return to_uint8(out)


def straighten(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate by ``angle`` degrees but keep the original frame size.

    Useful for levelling a slightly tilted horizon (the corners are cropped
    to the original bounds).
    """
    return rotate(img, angle, expand=False)


def flip(img: np.ndarray, mode: str = "h") -> np.ndarray:
    """Flip horizontally (``mode='h'``) or vertically (``mode='v'``)."""
    img = ensure_ndarray(img)
    if mode in ("h", "horizontal", "x"):
        return np.ascontiguousarray(img[:, ::-1])
    if mode in ("v", "vertical", "y"):
        return np.ascontiguousarray(img[::-1, :])
    raise ImgToolkitError("flip mode must be 'h' or 'v'")


def resize(img: np.ndarray, width=None, height=None, keep_aspect: bool = True,
           resample: str = "auto") -> np.ndarray:
    """Resize to ``width`` x ``height``.

    * Provide either dimension (or both). With ``keep_aspect`` True and both
      given, the image is scaled to *fit* inside the box (letterbox-free —
      it simply picks the smaller scale). With only one given, the other is
      derived from the aspect ratio.
    * ``resample``: ``'auto'`` (area when shrinking, cubic when enlarging),
      or one of nearest/bilinear/bicubic/area/lanczos.
    """
    img = ensure_ndarray(img)
    h, w = img.shape[:2]
    if width is None and height is None:
        raise ImgToolkitError("resize needs at least one of width/height")

    if keep_aspect:
        if width is not None and height is not None:
            scale = min(width / w, height / h)
            nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        elif width is not None:
            scale = width / w
            nw, nh = int(width), max(1, round(h * scale))
        else:
            scale = height / h
            nw, nh = max(1, round(w * scale)), int(height)
    else:
        nw = int(width) if width is not None else w
        nh = int(height) if height is not None else h
        nw, nh = max(1, nw), max(1, nh)

    shrinking = nw * nh < w * h
    out = cv2.resize(img, (nw, nh), interpolation=_interp(resample, shrinking))
    return to_uint8(out)


def _anchor_offsets(anchor: str, dx: int, dy: int):
    """Return (ox, oy) top-left offset for placing content in a larger canvas.

    ``dx``/``dy`` are the total slack (canvas - content) in each axis.
    """
    anchor = anchor.lower()
    horiz = {"left": 0.0, "center": 0.5, "centre": 0.5, "right": 1.0}
    vert = {"top": 0.0, "center": 0.5, "centre": 0.5, "bottom": 1.0}
    hx = vy = 0.5
    parts = anchor.replace("-", " ").replace("_", " ").split()
    for p in parts:
        if p in horiz:
            hx = horiz[p]
        if p in vert:
            vy = vert[p]
    if anchor in ("center", "centre"):
        hx = vy = 0.5
    return int(round(dx * hx)), int(round(dy * vy))


def canvas_resize(img: np.ndarray, width: int, height: int,
                  anchor: str = "center", fill=(0, 0, 0, 0)) -> np.ndarray:
    """Place ``img`` on a ``width`` x ``height`` canvas without scaling.

    Content larger than the canvas is cropped; smaller content is padded
    with ``fill``. ``anchor`` positions the content, e.g. ``'center'``,
    ``'top-left'``, ``'bottom-right'``.
    """
    img = ensure_ndarray(img)
    h, w = img.shape[:2]
    width, height = int(width), int(height)
    channels = img.shape[2] if img.ndim == 3 else 1
    if channels == 1:
        canvas = np.full((height, width), fill[0], dtype=np.uint8)
    else:
        canvas = np.zeros((height, width, channels), dtype=np.uint8)
        canvas[:, :] = np.array(fill[:channels], dtype=np.uint8)

    ox, oy = _anchor_offsets(anchor, width - w, height - h)

    # Source and destination regions (handle both crop and pad).
    sx0 = max(0, -ox)
    sy0 = max(0, -oy)
    dx0 = max(0, ox)
    dy0 = max(0, oy)
    cw = min(w - sx0, width - dx0)
    ch = min(h - sy0, height - dy0)
    if cw > 0 and ch > 0:
        canvas[dy0:dy0 + ch, dx0:dx0 + cw] = img[sy0:sy0 + ch, sx0:sx0 + cw]
    return canvas


def perspective_correct(img: np.ndarray, src_quad, out_size=None) -> np.ndarray:
    """Warp the quadrilateral ``src_quad`` to a rectangle.

    ``src_quad`` is 4 ``(x, y)`` points in order
    top-left, top-right, bottom-right, bottom-left. ``out_size`` is
    ``(width, height)``; when omitted it is estimated from the quad's edge
    lengths. Uses ``cv2.getPerspectiveTransform`` / ``warpPerspective``.
    """
    img = ensure_ndarray(img)
    src = np.asarray(src_quad, dtype=np.float32)
    if src.shape != (4, 2):
        raise ImgToolkitError("src_quad must be 4 (x, y) points")

    if out_size is None:
        (tl, tr, br, bl) = src
        widthA = np.linalg.norm(br - bl)
        widthB = np.linalg.norm(tr - tl)
        heightA = np.linalg.norm(tr - br)
        heightB = np.linalg.norm(tl - bl)
        ow = int(round(max(widthA, widthB)))
        oh = int(round(max(heightA, heightB)))
    else:
        ow, oh = int(out_size[0]), int(out_size[1])
    ow, oh = max(1, ow), max(1, oh)

    dst = np.array([[0, 0], [ow - 1, 0], [ow - 1, oh - 1], [0, oh - 1]],
                   dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(img, M, (ow, oh), flags=cv2.INTER_CUBIC)
    return to_uint8(out)
