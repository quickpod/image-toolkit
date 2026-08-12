"""Colour and tone adjustments.

All functions take an RGB/RGBA ``uint8`` ndarray and return a new one; alpha
is preserved untouched. Internally most work happens in float32.
"""

from __future__ import annotations

import cv2
import numpy as np

from ._util import apply_on_rgb, ensure_ndarray, split_alpha, to_uint8
from .errors import ImgToolkitError


def _f(img):
    return img.astype(np.float32)


def brightness(img: np.ndarray, factor: float) -> np.ndarray:
    """Scale brightness. ``factor`` 1.0 = unchanged, >1 brighter, <1 darker."""
    ensure_ndarray(img)
    return apply_on_rgb(img, lambda x: to_uint8(_f(x) * float(factor)))


def contrast(img: np.ndarray, factor: float) -> np.ndarray:
    """Adjust contrast about mid-grey (128). ``factor`` 1.0 = unchanged."""
    ensure_ndarray(img)
    f = float(factor)
    return apply_on_rgb(img, lambda x: to_uint8((_f(x) - 128.0) * f + 128.0))


def exposure(img: np.ndarray, ev: float) -> np.ndarray:
    """Exposure adjustment in stops (EV). +1 EV doubles the linear signal."""
    ensure_ndarray(img)
    gain = float(2.0 ** ev)
    return apply_on_rgb(img, lambda x: to_uint8(_f(x) * gain))


def highlights_shadows(img: np.ndarray, highlights: float = 0.0,
                       shadows: float = 0.0) -> np.ndarray:
    """Recover highlights / lift shadows.

    ``highlights`` in [-1, 1]: negative darkens bright areas (recovery).
    ``shadows`` in [-1, 1]: positive brightens dark areas (lift).
    A smooth luminance-based mask keeps mid-tones stable.
    """
    ensure_ndarray(img)

    def op(x):
        xf = _f(x) / 255.0
        lum = xf @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        lum = lum[..., None]
        # highlight mask ~1 in bright, shadow mask ~1 in dark regions
        hmask = np.clip((lum - 0.5) * 2.0, 0, 1)
        smask = np.clip((0.5 - lum) * 2.0, 0, 1)
        out = xf + shadows * smask * (1.0 - xf) * 0.8
        out = out + highlights * hmask * (xf) * 0.8
        return to_uint8(np.clip(out, 0, 1) * 255.0)

    return apply_on_rgb(img, op)


def saturation(img: np.ndarray, factor: float) -> np.ndarray:
    """Scale colour saturation. ``factor`` 1.0 = unchanged, 0 = grayscale."""
    ensure_ndarray(img)

    def op(x):
        hsv = cv2.cvtColor(x, cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * float(factor), 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    return apply_on_rgb(img, op)


def vibrance(img: np.ndarray, amount: float) -> np.ndarray:
    """Vibrance: boosts low-saturation pixels more than already-saturated ones.

    ``amount`` in roughly [-1, 1] (positive = more vivid). Protects skin
    tones better than a flat saturation boost.
    """
    ensure_ndarray(img)

    def op(x):
        hsv = cv2.cvtColor(x, cv2.COLOR_RGB2HSV).astype(np.float32)
        s = hsv[:, :, 1] / 255.0
        # weight: less-saturated pixels get boosted more.
        boost = amount * (1.0 - s)
        hsv[:, :, 1] = np.clip((s + boost) * 255.0, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    return apply_on_rgb(img, op)


def hue_shift(img: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate hue by ``degrees`` (0..360)."""
    ensure_ndarray(img)
    shift = (float(degrees) / 360.0) * 180.0  # OpenCV hue is 0..179

    def op(x):
        hsv = cv2.cvtColor(x, cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[:, :, 0] = np.mod(hsv[:, :, 0] + shift, 180.0)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    return apply_on_rgb(img, op)


def white_balance(img: np.ndarray, temp: float = 0.0, tint: float = 0.0,
                  auto: bool = False) -> np.ndarray:
    """White balance.

    * ``auto=True``: gray-world automatic white balance (ignores temp/tint).
    * otherwise: manual. ``temp`` in [-1, 1] warms (+) / cools (-);
      ``tint`` in [-1, 1] shifts green(-)/magenta(+).
    """
    ensure_ndarray(img)

    def op(x):
        xf = _f(x)
        if auto:
            means = xf.reshape(-1, 3).mean(axis=0)
            gray = means.mean()
            gain = gray / np.maximum(means, 1e-6)
            xf = xf * gain
        else:
            # temp: scale R up & B down (warm); tint: scale G / R+B.
            r_gain = 1.0 + 0.4 * temp
            b_gain = 1.0 - 0.4 * temp
            g_gain = 1.0 - 0.4 * tint
            m_gain = 1.0 + 0.2 * tint
            xf[:, :, 0] *= r_gain * m_gain
            xf[:, :, 1] *= g_gain
            xf[:, :, 2] *= b_gain * m_gain
        return to_uint8(xf)

    return apply_on_rgb(img, op)


def _lut_from_points(control_points):
    """Build a 256-entry uint8 LUT from monotonic (in, out) control points.

    Points are in the 0..255 domain. Linear interpolation between them,
    clamped at the ends.
    """
    pts = sorted((float(a), float(b)) for a, b in control_points)
    xs = np.array([p[0] for p in pts], dtype=np.float32)
    ys = np.array([p[1] for p in pts], dtype=np.float32)
    grid = np.arange(256, dtype=np.float32)
    lut = np.interp(grid, xs, ys)
    return np.clip(lut, 0, 255).astype(np.uint8)


def curves(img: np.ndarray, channel: str, control_points) -> np.ndarray:
    """Apply a tone curve defined by ``control_points`` = list of (in, out).

    ``channel`` is one of ``'rgb'`` (all channels), ``'r'``, ``'g'``, ``'b'``,
    or ``'luma'``. Values are in the 0..255 domain. Points need not be
    pre-sorted; the curve is piecewise-linear between them.
    """
    ensure_ndarray(img)
    lut = _lut_from_points(control_points)
    channel = channel.lower()

    def op(x):
        out = x.copy()
        if channel in ("rgb", "all", "value", "luma"):
            if channel == "luma":
                # apply to luminance, preserve chroma via YCrCb
                ycc = cv2.cvtColor(x, cv2.COLOR_RGB2YCrCb)
                ycc[:, :, 0] = lut[ycc[:, :, 0]]
                return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
            return lut[x]
        idx = {"r": 0, "g": 1, "b": 2}.get(channel)
        if idx is None:
            raise ImgToolkitError(f"Unknown curve channel '{channel}'")
        out[:, :, idx] = lut[x[:, :, idx]]
        return out

    return apply_on_rgb(img, op)


def levels(img: np.ndarray, in_black: float = 0, in_white: float = 255,
           gamma: float = 1.0, out_black: float = 0,
           out_white: float = 255) -> np.ndarray:
    """Photoshop-style levels adjustment.

    Maps input range [``in_black``, ``in_white``] to output range
    [``out_black``, ``out_white``] with a ``gamma`` midtone curve.
    """
    ensure_ndarray(img)
    in_black, in_white = float(in_black), float(in_white)
    out_black, out_white = float(out_black), float(out_white)
    gamma = max(1e-3, float(gamma))
    if in_white <= in_black:
        raise ImgToolkitError("levels: in_white must exceed in_black")

    grid = np.arange(256, dtype=np.float32)
    norm = np.clip((grid - in_black) / (in_white - in_black), 0, 1)
    norm = norm ** (1.0 / gamma)
    lut = (out_black + norm * (out_white - out_black)).clip(0, 255).astype(np.uint8)
    return apply_on_rgb(img, lambda x: lut[x])


def color_balance(img: np.ndarray, shadows=(0, 0, 0), midtones=(0, 0, 0),
                  highlights=(0, 0, 0)) -> np.ndarray:
    """Add per-tonal-range RGB offsets.

    Each argument is an ``(r, g, b)`` offset in roughly [-100, 100] applied
    to the shadow / midtone / highlight range respectively, weighted by a
    smooth luminance mask.
    """
    ensure_ndarray(img)

    def op(x):
        xf = _f(x)
        lum = (xf @ np.array([0.299, 0.587, 0.114], dtype=np.float32)) / 255.0
        lum = lum[..., None]
        w_shadow = np.clip(1.0 - lum * 2.0, 0, 1)
        w_high = np.clip((lum - 0.5) * 2.0, 0, 1)
        w_mid = 1.0 - w_shadow - w_high
        s = np.array(shadows, np.float32)
        m = np.array(midtones, np.float32)
        h = np.array(highlights, np.float32)
        xf = xf + w_shadow * s + w_mid * m + w_high * h
        return to_uint8(xf)

    return apply_on_rgb(img, op)


def grayscale(img: np.ndarray, keep_channels: bool = True) -> np.ndarray:
    """Convert to grayscale using Rec.601 luma.

    ``keep_channels`` True returns a 3-channel image where R==G==B (handy for
    compositing); False returns a 2-D single-channel image. Alpha preserved.
    """
    ensure_ndarray(img)
    rgb, alpha = split_alpha(img)
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if keep_channels:
        out = np.repeat(g[:, :, None], 3, axis=2)
        if alpha is not None:
            return np.dstack([out, alpha])
        return out
    return g  # 2-D; alpha dropped intentionally in single-channel mode


def invert(img: np.ndarray) -> np.ndarray:
    """Photographic negative (alpha preserved)."""
    ensure_ndarray(img)
    return apply_on_rgb(img, lambda x: 255 - x)


def sepia(img: np.ndarray, intensity: float = 1.0) -> np.ndarray:
    """Apply a sepia tone. ``intensity`` in [0, 1] blends with the original."""
    ensure_ndarray(img)
    m = np.array([
        [0.393, 0.769, 0.189],
        [0.349, 0.686, 0.168],
        [0.272, 0.534, 0.131],
    ], dtype=np.float32)

    def op(x):
        xf = _f(x)
        toned = xf @ m.T
        toned = np.clip(toned, 0, 255)
        out = xf * (1.0 - intensity) + toned * intensity
        return to_uint8(out)

    return apply_on_rgb(img, op)


def autocontrast(img: np.ndarray, clip_percent: float = 0.5) -> np.ndarray:
    """Stretch contrast so the ``clip_percent`` tails hit pure black/white."""
    ensure_ndarray(img)

    def op(x):
        out = np.empty_like(x)
        for c in range(x.shape[2]):
            ch = x[:, :, c]
            lo = np.percentile(ch, clip_percent)
            hi = np.percentile(ch, 100 - clip_percent)
            if hi <= lo:
                out[:, :, c] = ch
            else:
                stretched = (ch.astype(np.float32) - lo) / (hi - lo) * 255.0
                out[:, :, c] = to_uint8(stretched)
        return out

    return apply_on_rgb(img, op)


def auto_enhance(img: np.ndarray) -> np.ndarray:
    """One-click enhance: autocontrast + gray-world WB + mild saturation."""
    ensure_ndarray(img)
    out = autocontrast(img, clip_percent=0.5)
    out = white_balance(out, auto=True)
    out = saturation(out, 1.12)
    return out
