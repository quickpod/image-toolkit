"""Internal helpers shared across imgtoolkit modules.

Convention used throughout the package:

* Images are ``numpy.ndarray`` with dtype ``uint8``.
* Colour images are **RGB** (3 channels) or **RGBA** (4 channels), i.e.
  channel order matches Pillow, *not* OpenCV's BGR. Conversion to/from BGR
  happens only at the boundary of functions that call into ``cv2``.
* Grayscale images are 2-D ``(H, W)`` arrays.

These helpers are private (underscore module); public API lives in the
named feature modules.
"""

from __future__ import annotations

import numpy as np

from .errors import ImgToolkitError

try:  # cv2 is a hard dependency, but import lazily-friendly for clarity.
    import cv2
except Exception as exc:  # pragma: no cover - cv2 is required
    raise ImgToolkitError(f"OpenCV (cv2) is required but failed to import: {exc}")


def ensure_ndarray(img) -> np.ndarray:
    """Return ``img`` as an ndarray or raise :class:`ImgToolkitError`."""
    if not isinstance(img, np.ndarray):
        raise ImgToolkitError(
            f"Expected a numpy image array, got {type(img).__name__}"
        )
    if img.ndim not in (2, 3):
        raise ImgToolkitError(f"Unsupported image ndim: {img.ndim}")
    if img.ndim == 3 and img.shape[2] not in (1, 3, 4):
        raise ImgToolkitError(f"Unsupported channel count: {img.shape[2]}")
    return img


def to_uint8(img: np.ndarray) -> np.ndarray:
    """Clip to [0, 255] and cast to uint8 (float-safe)."""
    if img.dtype == np.uint8:
        return img
    return np.clip(img, 0, 255).astype(np.uint8)


def as_float(img: np.ndarray) -> np.ndarray:
    """Return a float32 copy of ``img`` (values kept in the 0..255 range)."""
    return img.astype(np.float32)


def has_alpha(img: np.ndarray) -> bool:
    """True if ``img`` is RGBA (or any 4-channel image)."""
    return img.ndim == 3 and img.shape[2] == 4


def is_gray(img: np.ndarray) -> bool:
    """True for a 2-D single-channel image."""
    return img.ndim == 2 or (img.ndim == 3 and img.shape[2] == 1)


def split_alpha(img: np.ndarray):
    """Split RGBA into (rgb, alpha). For RGB returns (img, None)."""
    if has_alpha(img):
        return np.ascontiguousarray(img[:, :, :3]), np.ascontiguousarray(img[:, :, 3])
    return img, None


def merge_alpha(rgb: np.ndarray, alpha: np.ndarray | None) -> np.ndarray:
    """Recombine an RGB array with an optional alpha channel."""
    if alpha is None:
        return rgb
    if rgb.ndim == 2:
        rgb = np.repeat(rgb[:, :, None], 3, axis=2)
    out = np.dstack([rgb, alpha])
    return np.ascontiguousarray(out)


def to_rgb(img: np.ndarray) -> np.ndarray:
    """Return a 3-channel RGB view of any supported image (drops alpha)."""
    if img.ndim == 2:
        return np.repeat(img[:, :, None], 3, axis=2)
    if img.shape[2] == 1:
        return np.repeat(img, 3, axis=2)
    if img.shape[2] == 4:
        return np.ascontiguousarray(img[:, :, :3])
    return img


def rgb_to_bgr(img: np.ndarray) -> np.ndarray:
    """RGB(A) -> BGR(A) for handing to OpenCV."""
    if img.ndim == 2:
        return img
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_RGBA2BGRA)
    return img


def bgr_to_rgb(img: np.ndarray) -> np.ndarray:
    """BGR(A) -> RGB(A) coming back from OpenCV."""
    if img.ndim == 2:
        return img
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    return img


def apply_on_rgb(img: np.ndarray, fn):
    """Apply ``fn`` to the RGB channels, preserving any alpha channel.

    ``fn`` takes and returns an RGB (or gray) uint8 ndarray.
    """
    rgb, alpha = split_alpha(img)
    out = fn(rgb)
    return merge_alpha(out, alpha)


def copy(img: np.ndarray) -> np.ndarray:
    """Defensive contiguous copy."""
    return np.ascontiguousarray(img.copy())
