"""Image filters and artistic effects.

Blur, sharpen, vignette, HDR-look, vintage/film, and OpenCV-backed artistic
styles (pencil sketch, stylize, cartoon, oil). Also a parser + applier for
Adobe ``.cube`` 3D LUTs.

All functions take/return RGB/RGBA ``uint8`` ndarrays; alpha is preserved.
Randomness (grain) is seeded for deterministic output.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from ._util import (apply_on_rgb, bgr_to_rgb, ensure_ndarray, rgb_to_bgr,
                    split_alpha, to_uint8)
from .errors import ImgToolkitError


def gaussian_blur(img: np.ndarray, radius: float = 3.0) -> np.ndarray:
    """Gaussian blur. ``radius`` ~ standard deviation in pixels."""
    ensure_ndarray(img)
    sigma = max(0.1, float(radius))
    k = int(sigma * 3) | 1  # odd kernel spanning ~3 sigma
    k = max(3, k)
    return apply_on_rgb(img, lambda x: cv2.GaussianBlur(x, (k, k), sigma))


def motion_blur(img: np.ndarray, angle: float = 0.0, distance: int = 15) -> np.ndarray:
    """Directional motion blur.

    ``angle`` in degrees (0 = horizontal), ``distance`` = streak length in px.
    """
    ensure_ndarray(img)
    distance = max(1, int(distance))
    kernel = np.zeros((distance, distance), dtype=np.float32)
    kernel[distance // 2, :] = 1.0
    M = cv2.getRotationMatrix2D((distance / 2 - 0.5, distance / 2 - 0.5), angle, 1.0)
    kernel = cv2.warpAffine(kernel, M, (distance, distance))
    s = kernel.sum()
    if s > 0:
        kernel /= s
    return apply_on_rgb(img, lambda x: to_uint8(cv2.filter2D(x, -1, kernel)))


def lens_blur(img: np.ndarray, radius: int = 7) -> np.ndarray:
    """Approximate lens/bokeh blur with a circular (disc) kernel."""
    ensure_ndarray(img)
    r = max(1, int(radius))
    size = 2 * r + 1
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    disc = (xx * xx + yy * yy) <= r * r
    kernel = disc.astype(np.float32)
    kernel /= kernel.sum()
    return apply_on_rgb(img, lambda x: to_uint8(cv2.filter2D(x, -1, kernel)))


def sharpen(img: np.ndarray, amount: float = 1.0, radius: float = 2.0,
            threshold: int = 0) -> np.ndarray:
    """Unsharp-mask sharpening.

    ``amount`` = strength (1.0 typical), ``radius`` = blur sigma of the mask,
    ``threshold`` = minimum contrast (0..255) before a pixel is sharpened.
    """
    ensure_ndarray(img)
    sigma = max(0.1, float(radius))
    k = max(3, int(sigma * 3) | 1)

    def op(x):
        blurred = cv2.GaussianBlur(x, (k, k), sigma).astype(np.float32)
        xf = x.astype(np.float32)
        mask = xf - blurred
        if threshold > 0:
            low = np.abs(mask) < threshold
            mask[low] = 0
        return to_uint8(xf + amount * mask)

    return apply_on_rgb(img, op)


# Convenience alias matching the spec wording.
unsharp_mask = sharpen


def vignette(img: np.ndarray, strength: float = 0.6, radius: float = 1.0) -> np.ndarray:
    """Darken the edges. ``strength`` in [0, 1]; ``radius`` scales the falloff."""
    ensure_ndarray(img)

    def op(x):
        h, w = x.shape[:2]
        ky = cv2.getGaussianKernel(h, h * 0.5 * radius)
        kx = cv2.getGaussianKernel(w, w * 0.5 * radius)
        mask = ky @ kx.T
        mask = mask / mask.max()
        mask = 1.0 - strength * (1.0 - mask)
        return to_uint8(x.astype(np.float32) * mask[:, :, None])

    return apply_on_rgb(img, op)


def hdr_effect(img: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """HDR-look local-contrast boost via ``cv2.detailEnhance``.

    This is a single-image *effect*, not a true exposure merge (see
    :func:`imgtoolkit.effects_advanced.hdr_merge` for merging brackets).
    """
    ensure_ndarray(img)
    sigma_s = 12.0
    sigma_r = 0.15 + 0.3 * float(strength)

    def op(x):
        bgr = rgb_to_bgr(x)
        out = cv2.detailEnhance(bgr, sigma_s=sigma_s, sigma_r=sigma_r)
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


def vintage(img: np.ndarray, fade: float = 0.2, grain: float = 12.0,
            seed: int = 0) -> np.ndarray:
    """Vintage / film look: warm curve + faded blacks + monochrome grain.

    ``fade`` lifts the blacks (0..1), ``grain`` = grain std-dev in levels.
    ``seed`` makes the grain deterministic.
    """
    ensure_ndarray(img)

    def op(x):
        xf = x.astype(np.float32)
        # Warm the highlights, cool the shadows slightly.
        xf[:, :, 0] = np.clip(xf[:, :, 0] * 1.06 + 8, 0, 255)   # R up
        xf[:, :, 2] = np.clip(xf[:, :, 2] * 0.94, 0, 255)       # B down
        # Fade: lift the black point.
        lift = fade * 255.0
        xf = lift + xf * (255.0 - lift) / 255.0
        # Grain.
        if grain > 0:
            rng = np.random.default_rng(seed)
            noise = rng.normal(0, grain, xf.shape[:2]).astype(np.float32)
            xf += noise[:, :, None]
        return to_uint8(xf)

    return apply_on_rgb(img, op)


# Alias
film = vintage


def pencil_sketch(img: np.ndarray, color: bool = False) -> np.ndarray:
    """Pencil-sketch effect via ``cv2.pencilSketch``.

    ``color`` False returns the grayscale sketch, True the colour version.
    """
    ensure_ndarray(img)

    def op(x):
        bgr = rgb_to_bgr(x)
        gray, col = cv2.pencilSketch(bgr, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
        if color:
            return bgr_to_rgb(col)
        return np.repeat(gray[:, :, None], 3, axis=2)

    return apply_on_rgb(img, op)


def stylize(img: np.ndarray) -> np.ndarray:
    """Watercolour-ish stylization via ``cv2.stylization``."""
    ensure_ndarray(img)

    def op(x):
        bgr = rgb_to_bgr(x)
        out = cv2.stylization(bgr, sigma_s=60, sigma_r=0.45)
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


def oil_paint(img: np.ndarray, size: int = 7, dyn_ratio: int = 1) -> np.ndarray:
    """Oil-painting effect.

    Uses ``cv2.xphoto.oilPainting`` when available, else a fast
    morphological/edge-preserving approximation.
    """
    ensure_ndarray(img)

    def op(x):
        bgr = rgb_to_bgr(x)
        try:
            out = cv2.xphoto.oilPainting(bgr, int(size), int(dyn_ratio))
        except Exception:
            # Approximation: heavy edge-preserving smoothing + posterize.
            out = cv2.edgePreservingFilter(bgr, flags=1, sigma_s=size * 8,
                                           sigma_r=0.4)
            out = (out // 24) * 24
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


def cartoon(img: np.ndarray) -> np.ndarray:
    """Cartoon effect: edge mask over a colour-quantised, smoothed image."""
    ensure_ndarray(img)

    def op(x):
        bgr = rgb_to_bgr(x)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY, 9, 9)
        color = cv2.bilateralFilter(bgr, 9, 250, 250)
        out = cv2.bitwise_and(color, color, mask=edges)
        return bgr_to_rgb(out)

    return apply_on_rgb(img, op)


# ---------------------------------------------------------------------------
# .cube 3D LUT parsing / application
# ---------------------------------------------------------------------------

def parse_cube_lut(path: str):
    """Parse an Adobe ``.cube`` 3D LUT file.

    Returns ``(table, size, domain_min, domain_max)`` where ``table`` is a
    ``(size, size, size, 3)`` float array indexed ``[b, g, r]`` per the .cube
    spec (r varies fastest). Raises :class:`ImgToolkitError` on a malformed
    file. 1D LUTs are not supported.
    """
    if not os.path.isfile(path):
        raise ImgToolkitError(f"LUT file not found: {path}")
    size = None
    dmin = np.array([0.0, 0.0, 0.0], np.float32)
    dmax = np.array([1.0, 1.0, 1.0], np.float32)
    values = []
    try:
        with open(path, "r") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                up = line.upper()
                if up.startswith("TITLE"):
                    continue
                if up.startswith("LUT_3D_SIZE"):
                    size = int(line.split()[-1])
                elif up.startswith("LUT_1D_SIZE"):
                    raise ImgToolkitError("1D .cube LUTs are not supported")
                elif up.startswith("DOMAIN_MIN"):
                    dmin = np.array([float(v) for v in line.split()[1:4]], np.float32)
                elif up.startswith("DOMAIN_MAX"):
                    dmax = np.array([float(v) for v in line.split()[1:4]], np.float32)
                elif up.startswith("LUT_3D_INPUT_RANGE"):
                    parts = line.split()
                    dmin = np.array([float(parts[1])] * 3, np.float32)
                    dmax = np.array([float(parts[2])] * 3, np.float32)
                else:
                    parts = line.split()
                    if len(parts) == 3:
                        values.append([float(p) for p in parts])
    except ImgToolkitError:
        raise
    except Exception as exc:
        raise ImgToolkitError(f"Failed to parse LUT {path}: {exc}")

    if size is None:
        raise ImgToolkitError("LUT_3D_SIZE not found in .cube file")
    if len(values) != size ** 3:
        raise ImgToolkitError(
            f"LUT has {len(values)} entries, expected {size ** 3}"
        )
    table = np.array(values, dtype=np.float32).reshape(size, size, size, 3)
    return table, size, dmin, dmax


def apply_lut(img: np.ndarray, cube_path: str) -> np.ndarray:
    """Apply a 3D ``.cube`` LUT to ``img`` (trilinear interpolation)."""
    ensure_ndarray(img)
    table, size, dmin, dmax = parse_cube_lut(cube_path)

    def op(x):
        xf = x.astype(np.float32) / 255.0
        span = np.maximum(dmax - dmin, 1e-6)
        norm = np.clip((xf - dmin) / span, 0, 1)
        coord = norm * (size - 1)
        i0 = np.floor(coord).astype(np.int32)
        i1 = np.minimum(i0 + 1, size - 1)
        frac = coord - i0

        r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
        r1, g1, b1 = i1[..., 0], i1[..., 1], i1[..., 2]
        fr = frac[..., 0:1]
        fg = frac[..., 1:2]
        fb = frac[..., 2:3]

        # table indexed [b, g, r]
        def T(bi, gi, ri):
            return table[bi, gi, ri]

        c000 = T(b0, g0, r0)
        c100 = T(b0, g0, r1)
        c010 = T(b0, g1, r0)
        c110 = T(b0, g1, r1)
        c001 = T(b1, g0, r0)
        c101 = T(b1, g0, r1)
        c011 = T(b1, g1, r0)
        c111 = T(b1, g1, r1)

        c00 = c000 * (1 - fr) + c100 * fr
        c01 = c001 * (1 - fr) + c101 * fr
        c10 = c010 * (1 - fr) + c110 * fr
        c11 = c011 * (1 - fr) + c111 * fr
        c0 = c00 * (1 - fg) + c10 * fg
        c1 = c01 * (1 - fg) + c11 * fg
        out = c0 * (1 - fb) + c1 * fb
        return to_uint8(np.clip(out, 0, 1) * 255.0)

    return apply_on_rgb(img, op)
