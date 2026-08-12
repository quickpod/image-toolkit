"""Retouching: healing, inpainting, red-eye, skin smoothing, denoise.

The inpainting-based functions (:func:`heal`, :func:`spot_removal`,
:func:`object_removal`) use **CLASSICAL** image inpainting
(``cv2.inpaint``: Telea / Navier-Stokes). They are *not* deep-learning
generative fill and do not depend on any ML model weights.

All functions take/return RGB/RGBA ``uint8`` ndarrays; alpha is preserved.
"""

from __future__ import annotations

import cv2
import numpy as np

from ._util import (apply_on_rgb, bgr_to_rgb, ensure_ndarray, rgb_to_bgr,
                    split_alpha)
from .errors import ImgToolkitError

_METHODS = {"telea": cv2.INPAINT_TELEA, "ns": cv2.INPAINT_NS}


def _binary_mask(mask, shape):
    """Coerce a mask to a uint8 0/255 single-channel array of ``shape``."""
    m = np.asarray(mask)
    if m.ndim == 3:
        m = m[:, :, 0]
    if m.shape != shape:
        raise ImgToolkitError(
            f"mask shape {m.shape} does not match image {shape}"
        )
    return np.where(m > 0, 255, 0).astype(np.uint8)


def heal(img: np.ndarray, mask=None, point=None, radius: int = 10,
         method: str = "telea") -> np.ndarray:
    """Heal a region using CLASSICAL inpainting (``cv2.inpaint``).

    Provide **either** a ``mask`` (non-zero = heal) **or** a ``point``
    ``(x, y)`` with a ``radius`` to synthesise a circular mask. ``method`` is
    ``'telea'`` (fast marching) or ``'ns'`` (Navier-Stokes).

    This is not deep-learning inpainting; it interpolates from surrounding
    pixels and works best on small blemishes.
    """
    ensure_ndarray(img)
    if method not in _METHODS:
        raise ImgToolkitError("method must be 'telea' or 'ns'")
    h, w = img.shape[:2]

    if mask is None:
        if point is None:
            raise ImgToolkitError("heal needs either a mask or a point")
        m = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(m, (int(point[0]), int(point[1])), int(radius), 255, -1)
    else:
        m = _binary_mask(mask, (h, w))

    def op(x):
        bgr = rgb_to_bgr(x)
        out = cv2.inpaint(bgr, m, int(radius), _METHODS[method])
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


# Aliases with intent-revealing names.
def spot_removal(img, point, radius=10, method="telea"):
    """Remove a small blemish at ``point`` = (x, y). CLASSICAL inpainting."""
    return heal(img, point=point, radius=radius, method=method)


def object_removal(img, mask, method="telea", radius=10):
    """Remove a masked object via CLASSICAL inpainting (not generative AI)."""
    return heal(img, mask=mask, radius=radius, method=method)


def clone_stamp(img: np.ndarray, src, dst, radius: int = 15,
                feather: float = 0.4) -> np.ndarray:
    """Programmatic clone-stamp: copy a circular patch from ``src`` to ``dst``.

    ``src``/``dst`` are ``(x, y)`` centres. A feathered circular mask blends
    the patch in. This is the headless/testable core; the interactive brush
    lives in the GUI.
    """
    ensure_ndarray(img)
    h, w = img.shape[:2]
    r = int(radius)
    sx, sy = int(src[0]), int(src[1])
    dx, dy = int(dst[0]), int(dst[1])

    # Build a feathered circular alpha mask in patch space.
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    dist = np.sqrt(xx * xx + yy * yy) / max(1, r)
    alpha = np.clip((1.0 - dist) / max(1e-3, feather), 0, 1).astype(np.float32)

    def op(x):
        out = x.copy().astype(np.float32)
        for j in range(-r, r + 1):
            for i in range(-r, r + 1):
                a = alpha[j + r, i + r]
                if a <= 0:
                    continue
                syy, sxx = sy + j, sx + i
                dyy, dxx = dy + j, dx + i
                if not (0 <= syy < h and 0 <= sxx < w):
                    continue
                if not (0 <= dyy < h and 0 <= dxx < w):
                    continue
                out[dyy, dxx] = out[dyy, dxx] * (1 - a) + x[syy, sxx] * a
        return np.clip(out, 0, 255).astype(np.uint8)

    return apply_on_rgb(img, op)


def red_eye_removal(img: np.ndarray, region) -> np.ndarray:
    """Reduce red-eye inside ``region`` = ``(left, top, right, bottom)``.

    Detects strongly-red pixels (R dominant over G/B) and desaturates them to
    a neutral dark grey, preserving the catch-light.
    """
    ensure_ndarray(img)
    rgb, alpha = split_alpha(img)
    out = rgb.copy()
    l, t, r, b = [int(v) for v in region]
    l, t = max(0, l), max(0, t)
    r, b = min(rgb.shape[1], r), min(rgb.shape[0], b)
    if r <= l or b <= t:
        raise ImgToolkitError("red_eye region is empty or out of bounds")

    patch = out[t:b, l:r].astype(np.float32)
    R, G, B = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    redness = R / (G + B + 1.0)
    mask = (redness > 1.5) & (R > 60)
    gray = (G + B) / 2.0
    R[mask] = gray[mask]
    G[mask] = gray[mask]
    B[mask] = gray[mask]
    out[t:b, l:r] = np.clip(patch, 0, 255).astype(np.uint8)

    if alpha is not None:
        return np.dstack([out, alpha])
    return out


def skin_smooth(img: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Edge-preserving skin smoothing (bilateral). ``strength`` in [0, 1]."""
    ensure_ndarray(img)
    d = int(5 + 10 * strength)
    sigma = 30 + 70 * strength

    def op(x):
        bgr = rgb_to_bgr(x)
        smoothed = cv2.bilateralFilter(bgr, d, sigma, sigma)
        # Blend so texture is softened, not obliterated.
        out = cv2.addWeighted(smoothed, 0.7, bgr, 0.3, 0)
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


def denoise(img: np.ndarray, strength: float = 10.0) -> np.ndarray:
    """Colour denoise via ``cv2.fastNlMeansDenoisingColored``.

    ``strength`` (~luminance filter h). Higher removes more noise but softens
    detail.
    """
    ensure_ndarray(img)
    h = float(strength)

    def op(x):
        bgr = rgb_to_bgr(x)
        out = cv2.fastNlMeansDenoisingColored(bgr, None, h, h, 7, 21)
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


def reduce_noise(img: np.ndarray, level: str = "medium") -> np.ndarray:
    """Denoise with a named ``level``: 'low' | 'medium' | 'high'."""
    table = {"low": 5.0, "medium": 10.0, "high": 18.0}
    if level not in table:
        raise ImgToolkitError("level must be low/medium/high")
    return denoise(img, table[level])
