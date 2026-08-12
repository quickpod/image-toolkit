"""Advanced multi-step effects.

* content-aware scale (seam carving)
* liquify / local warp (push, bloat, pinch)
* panorama stitching (``cv2.Stitcher``)
* exposure-free HDR merge (``cv2.MergeMertens``)
* focus stacking (align + Laplacian sharpness selection)

Functions take/return RGB/RGBA ``uint8`` ndarrays unless noted. Multi-image
functions take a list of ndarrays.
"""

from __future__ import annotations

import cv2
import numpy as np

from ._util import bgr_to_rgb, ensure_ndarray, rgb_to_bgr, split_alpha, to_rgb, to_uint8
from .errors import ImgToolkitError

try:
    from skimage.transform import seam_carve as _sk_seam_carve
    _HAS_SK_SEAM = True
except Exception:
    _sk_seam_carve = None
    _HAS_SK_SEAM = False


# ---------------------------------------------------------------------------
# Content-aware scaling (seam carving)
# ---------------------------------------------------------------------------

def _energy(gray: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return np.abs(gx) + np.abs(gy)


def _remove_one_vertical_seam(img: np.ndarray) -> np.ndarray:
    """Remove one vertical seam of least energy. ``img`` is (H, W, C)."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    energy = _energy(gray)

    # DP cumulative energy.
    M = energy.copy()
    back = np.zeros((h, w), dtype=np.int32)
    for i in range(1, h):
        left = np.r_[np.inf, M[i - 1, :-1]]
        up = M[i - 1, :]
        right = np.r_[M[i - 1, 1:], np.inf]
        choices = np.vstack([left, up, right])
        argmin = np.argmin(choices, axis=0)  # 0=left,1=up,2=right
        back[i] = argmin - 1
        M[i] += np.min(choices, axis=0)

    # Backtrack the minimal seam.
    seam = np.zeros(h, dtype=np.int32)
    seam[-1] = int(np.argmin(M[-1]))
    for i in range(h - 2, -1, -1):
        j = seam[i + 1]
        seam[i] = min(max(j + back[i + 1, j], 0), w - 1)

    # Build output without the seam column.
    out = np.zeros((h, w - 1, img.shape[2]), dtype=img.dtype)
    for i in range(h):
        j = seam[i]
        out[i, :, :] = np.delete(img[i, :, :], j, axis=0)
    return out


def content_aware_scale(img: np.ndarray, width: int) -> np.ndarray:
    """Seam-carve the image to ``width`` pixels, keeping the height.

    Only width reduction is implemented (the common case and what the tests
    exercise). Uses scikit-image's ``seam_carve`` when available, otherwise a
    correct built-in DP seam remover. Raises if ``width`` >= current width.
    """
    img = ensure_ndarray(img)
    h, w = img.shape[:2]
    width = int(width)
    if width <= 0:
        raise ImgToolkitError("target width must be positive")
    if width >= w:
        raise ImgToolkitError(
            f"content_aware_scale only shrinks width ({width} >= {w})"
        )

    if _HAS_SK_SEAM:
        try:
            gray = cv2.cvtColor(to_rgb(img), cv2.COLOR_RGB2GRAY).astype(np.float64)
            energy = _energy(gray.astype(np.float32)).astype(np.float64)
            carved = _sk_seam_carve(img, energy, "vertical", w - width)
            return to_uint8(carved)
        except Exception:
            pass  # fall through to built-in

    out = img
    for _ in range(w - width):
        out = _remove_one_vertical_seam(out)
    return out


# ---------------------------------------------------------------------------
# Liquify / local warp
# ---------------------------------------------------------------------------

def liquify(img: np.ndarray, center, radius: float, strength: float,
            mode: str = "push", direction=(1.0, 0.0)) -> np.ndarray:
    """Local warp inside a circle via displacement remapping.

    * ``mode='bloat'`` pushes pixels outward (magnify), ``'pinch'`` inward,
      ``'push'`` shoves them along ``direction`` = (dx, dy).
    * ``center`` = (x, y), ``radius`` in px, ``strength`` roughly in [-1, 1]
      for bloat/pinch or px-scale for push.
    """
    img = ensure_ndarray(img)
    h, w = img.shape[:2]
    cx, cy = float(center[0]), float(center[1])
    r = float(radius)

    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = xs - cx
    dy = ys - cy
    dist = np.sqrt(dx * dx + dy * dy)
    within = dist < r
    falloff = np.zeros_like(dist)
    falloff[within] = (1.0 - dist[within] / r) ** 2

    map_x = xs.copy()
    map_y = ys.copy()

    if mode in ("bloat", "pinch"):
        sign = 1.0 if mode == "pinch" else -1.0
        scale = sign * strength * falloff
        map_x = xs + dx * scale
        map_y = ys + dy * scale
    elif mode == "push":
        d = np.array(direction, np.float32)
        n = np.linalg.norm(d)
        if n > 0:
            d = d / n
        map_x = xs - d[0] * strength * falloff
        map_y = ys - d[1] * strength * falloff
    else:
        raise ImgToolkitError("liquify mode must be push/bloat/pinch")

    out = cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REFLECT)
    return to_uint8(out)


# Convenience aliases.
def warp(img, center, radius, strength, direction=(1.0, 0.0)):
    """Push warp along ``direction`` (see :func:`liquify`)."""
    return liquify(img, center, radius, strength, mode="push", direction=direction)


# ---------------------------------------------------------------------------
# Panorama stitching
# ---------------------------------------------------------------------------

def panorama_stitch(images) -> np.ndarray:
    """Stitch overlapping ``images`` into a panorama via ``cv2.Stitcher``.

    Returns the stitched RGB image. Raises :class:`ImgToolkitError` if OpenCV
    cannot find enough matches (too little overlap / detail).
    """
    if len(images) < 2:
        raise ImgToolkitError("panorama_stitch needs at least 2 images")
    bgr = [rgb_to_bgr(to_rgb(ensure_ndarray(im))) for im in images]
    try:
        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
    except AttributeError:
        stitcher = cv2.Stitcher.create(cv2.Stitcher_PANORAMA)
    status, pano = stitcher.stitch(bgr)
    if status != cv2.Stitcher_OK:
        raise ImgToolkitError(
            f"panorama stitching failed (status {status}); "
            "images may not overlap enough or lack distinctive features"
        )
    return bgr_to_rgb(pano)


# ---------------------------------------------------------------------------
# HDR merge (exposure-free)
# ---------------------------------------------------------------------------

def hdr_merge(images, exposures=None) -> np.ndarray:
    """Merge bracketed exposures into a tone-mapped 8-bit image.

    Uses ``cv2.MergeMertens`` (exposure-fusion) which needs *no* exposure
    times and is robust. ``exposures`` is accepted for API symmetry but not
    required by Mertens fusion.
    """
    if len(images) < 2:
        raise ImgToolkitError("hdr_merge needs at least 2 images")
    bgr = [rgb_to_bgr(to_rgb(ensure_ndarray(im))) for im in images]
    shapes = {im.shape[:2] for im in bgr}
    if len(shapes) != 1:
        raise ImgToolkitError("hdr_merge inputs must share the same size")
    merge = cv2.createMergeMertens()
    fused = merge.process(bgr)  # float32 0..1
    out = np.clip(fused * 255.0, 0, 255).astype(np.uint8)
    return bgr_to_rgb(out)


# ---------------------------------------------------------------------------
# Focus stacking
# ---------------------------------------------------------------------------

def _align_to_reference(images_bgr):
    """Align each image to the first using ECC (translation)."""
    ref_gray = cv2.cvtColor(images_bgr[0], cv2.COLOR_BGR2GRAY).astype(np.float32)
    aligned = [images_bgr[0]]
    for im in images_bgr[1:]:
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
        warp_matrix = np.eye(2, 3, dtype=np.float32)
        try:
            criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
            cv2.findTransformECC(ref_gray, gray, warp_matrix,
                                 cv2.MOTION_TRANSLATION, criteria, None, 5)
            im = cv2.warpAffine(im, warp_matrix, (im.shape[1], im.shape[0]),
                                flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
        except cv2.error:
            pass  # keep unaligned if ECC fails to converge
        aligned.append(im)
    return aligned


def focus_stack(images, align: bool = True) -> np.ndarray:
    """Combine a focus bracket into an all-in-focus image.

    Aligns the frames (optional), measures per-pixel sharpness with a
    Laplacian, and selects the sharpest source at each pixel.
    """
    if len(images) < 2:
        raise ImgToolkitError("focus_stack needs at least 2 images")
    bgr = [rgb_to_bgr(to_rgb(ensure_ndarray(im))) for im in images]
    shapes = {im.shape[:2] for im in bgr}
    if len(shapes) != 1:
        raise ImgToolkitError("focus_stack inputs must share the same size")
    if align:
        bgr = _align_to_reference(bgr)

    laps = []
    for im in bgr:
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
        # local sharpness = blurred magnitude of the laplacian
        sharp = cv2.GaussianBlur(np.abs(lap), (5, 5), 0)
        laps.append(sharp)

    stack = np.stack(laps, axis=0)  # (N, H, W)
    best = np.argmax(stack, axis=0)  # (H, W)
    out = np.zeros_like(bgr[0])
    for idx in range(len(bgr)):
        mask = best == idx
        out[mask] = bgr[idx][mask]
    return bgr_to_rgb(out)
