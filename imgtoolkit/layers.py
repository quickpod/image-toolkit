"""Non-destructive layer / compositing model (headless).

This is the backbone of "layers / non-destructive editing". A
:class:`Document` holds an ordered list of layers (image layers and
adjustment layers), each with an ``opacity`` (0..1), a ``blend_mode`` and an
optional grayscale ``mask``. :meth:`Document.render` composites them
bottom-to-top and returns a single ndarray.

Compositing uses the standard W3C blending + Porter-Duff *source-over*
formula, computed in float (0..1). The blend-mode maths lives in
:data:`BLEND_MODES` and is unit-tested against hand-computed values.
"""

from __future__ import annotations

import numpy as np

from ._util import ensure_ndarray, has_alpha, to_uint8
from .errors import ImgToolkitError

# ---------------------------------------------------------------------------
# Blend-mode maths. Each takes (backdrop, source) float arrays in [0, 1] and
# returns the blended colour B(Cb, Cs) in [0, 1]. Applied per channel.
# ---------------------------------------------------------------------------


def _normal(cb, cs):
    return cs


def _multiply(cb, cs):
    return cb * cs


def _screen(cb, cs):
    return cb + cs - cb * cs


def _overlay(cb, cs):
    # overlay(cb, cs) == hardlight(cs, cb)
    return np.where(cb <= 0.5, 2 * cb * cs, 1 - 2 * (1 - cb) * (1 - cs))


def _darken(cb, cs):
    return np.minimum(cb, cs)


def _lighten(cb, cs):
    return np.maximum(cb, cs)


def _difference(cb, cs):
    return np.abs(cb - cs)


def _add(cb, cs):
    return np.minimum(cb + cs, 1.0)


def _soft_light(cb, cs):
    # W3C soft-light.
    d = np.where(cb <= 0.25, ((16 * cb - 12) * cb + 4) * cb, np.sqrt(cb))
    return np.where(
        cs <= 0.5,
        cb - (1 - 2 * cs) * cb * (1 - cb),
        cb + (2 * cs - 1) * (d - cb),
    )


BLEND_MODES = {
    "normal": _normal,
    "multiply": _multiply,
    "screen": _screen,
    "overlay": _overlay,
    "darken": _darken,
    "lighten": _lighten,
    "difference": _difference,
    "add": _add,
    "softlight": _soft_light,
}


def blend(backdrop, source, mode="normal"):
    """Return ``B(backdrop, source)`` for a named ``mode`` (arrays in [0, 1])."""
    if mode not in BLEND_MODES:
        raise ImgToolkitError(
            f"Unknown blend mode '{mode}'. Known: {sorted(BLEND_MODES)}"
        )
    return BLEND_MODES[mode](backdrop, source)


# ---------------------------------------------------------------------------
# Layer types
# ---------------------------------------------------------------------------

class Layer:
    """Base layer: opacity, blend mode, optional mask, visibility."""

    def __init__(self, opacity=1.0, blend_mode="normal", mask=None,
                 visible=True, name=None):
        if not 0.0 <= opacity <= 1.0:
            raise ImgToolkitError("opacity must be in [0, 1]")
        if blend_mode not in BLEND_MODES:
            raise ImgToolkitError(f"Unknown blend mode '{blend_mode}'")
        self.opacity = float(opacity)
        self.blend_mode = blend_mode
        self.visible = bool(visible)
        self.name = name
        self.mask = None
        if mask is not None:
            self.set_mask(mask)

    def set_mask(self, mask):
        """Attach a grayscale mask (2-D uint8/float, 0..255 or 0..1)."""
        m = np.asarray(mask)
        if m.ndim == 3:
            m = m[:, :, 0]
        m = m.astype(np.float32)
        if m.max() > 1.0:
            m = m / 255.0
        self.mask = np.clip(m, 0.0, 1.0)

    def _mask_for(self, shape):
        """Return the mask resampled/validated to (H, W), or None."""
        if self.mask is None:
            return None
        if self.mask.shape != shape:
            raise ImgToolkitError(
                f"mask shape {self.mask.shape} != layer size {shape}"
            )
        return self.mask


class ImageLayer(Layer):
    """A pixel layer holding an RGB or RGBA ``uint8`` image."""

    def __init__(self, image, opacity=1.0, blend_mode="normal", mask=None,
                 visible=True, name=None):
        super().__init__(opacity, blend_mode, mask, visible, name)
        self.image = ensure_ndarray(image)

    def rgb_alpha(self):
        """Return (rgb float 0..1 (H,W,3), alpha float 0..1 (H,W))."""
        img = self.image
        if img.ndim == 2:
            rgb = np.repeat(img[:, :, None], 3, axis=2).astype(np.float32) / 255.0
            alpha = np.ones(img.shape[:2], np.float32)
        elif has_alpha(img):
            rgb = img[:, :, :3].astype(np.float32) / 255.0
            alpha = img[:, :, 3].astype(np.float32) / 255.0
        else:
            rgb = img[:, :, :3].astype(np.float32) / 255.0
            alpha = np.ones(img.shape[:2], np.float32)
        return rgb, alpha


class AdjustmentLayer(Layer):
    """A non-destructive adjustment applied to the composite beneath it.

    ``func`` maps an RGB ``uint8`` ndarray to an RGB ``uint8`` ndarray (e.g.
    ``lambda x: color.brightness(x, 1.2)``). The effect is masked and scaled
    by the layer's opacity/mask.
    """

    def __init__(self, func, opacity=1.0, mask=None, visible=True, name=None):
        super().__init__(opacity, "normal", mask, visible, name)
        if not callable(func):
            raise ImgToolkitError("AdjustmentLayer needs a callable func")
        self.func = func


class Document:
    """An ordered stack of layers with a common canvas size.

    Layers are stored bottom-to-top (index 0 = bottom). All image/adjustment
    layers must match the document's ``(height, width)``.
    """

    def __init__(self, width=None, height=None, background=None):
        self.layers: list[Layer] = []
        self.width = int(width) if width else None
        self.height = int(height) if height else None
        # Optional opaque background colour (r, g, b) 0..255; None = transparent.
        self.background = background

    # -- layer management --------------------------------------------------
    def add_layer(self, layer: Layer) -> Layer:
        """Append a layer on top of the stack."""
        if not isinstance(layer, Layer):
            raise ImgToolkitError("add_layer expects a Layer instance")
        if isinstance(layer, ImageLayer):
            h, w = layer.image.shape[:2]
            if self.width is None:
                self.width, self.height = w, h
            elif (w, h) != (self.width, self.height):
                raise ImgToolkitError(
                    f"layer size {w}x{h} != document {self.width}x{self.height}"
                )
        self.layers.append(layer)
        return layer

    def add_image(self, image, **kw) -> ImageLayer:
        """Convenience: wrap ``image`` in an :class:`ImageLayer` and add it."""
        return self.add_layer(ImageLayer(image, **kw))

    def add_adjustment(self, func, **kw) -> AdjustmentLayer:
        """Convenience: add an :class:`AdjustmentLayer` from ``func``."""
        return self.add_layer(AdjustmentLayer(func, **kw))

    def remove_layer(self, index: int):
        try:
            return self.layers.pop(index)
        except IndexError:
            raise ImgToolkitError(f"no layer at index {index}")

    def move_layer(self, index: int, new_index: int):
        """Reorder a layer within the stack."""
        if not (0 <= index < len(self.layers)):
            raise ImgToolkitError("index out of range")
        layer = self.layers.pop(index)
        self.layers.insert(new_index, layer)

    # -- rendering ---------------------------------------------------------
    def render(self, keep_alpha=False) -> np.ndarray:
        """Composite all visible layers bottom-to-top into one ndarray.

        Returns RGBA ``uint8`` when ``keep_alpha`` is True, otherwise RGB
        (composited over ``self.background`` or black). Uses the W3C
        source-over blend formula in float.
        """
        if self.width is None or self.height is None:
            raise ImgToolkitError("document has no size (add a layer first)")
        h, w = self.height, self.width

        # Backdrop accumulator: colour (0..1) and alpha (0..1).
        cb = np.zeros((h, w, 3), np.float32)
        ab = np.zeros((h, w), np.float32)

        for layer in self.layers:
            if not layer.visible or layer.opacity <= 0:
                continue

            if isinstance(layer, ImageLayer):
                cs, src_alpha = layer.rgb_alpha()
                eff = src_alpha * layer.opacity
                mask = layer._mask_for((h, w))
                if mask is not None:
                    eff = eff * mask
                blended = blend(cb, cs, layer.blend_mode)
                # W3C: mix straight source with blended by backdrop alpha.
                cs_mixed = (1.0 - ab[..., None]) * cs + ab[..., None] * blended
                ao = eff + ab * (1.0 - eff)
                eff3 = eff[..., None]
                ab3 = ab[..., None]
                co_prem = eff3 * cs_mixed + (1.0 - eff3) * ab3 * cb
                with np.errstate(divide="ignore", invalid="ignore"):
                    cb_new = np.where(ao[..., None] > 1e-6,
                                      co_prem / np.maximum(ao[..., None], 1e-6),
                                      0.0)
                cb, ab = cb_new.astype(np.float32), ao.astype(np.float32)

            elif isinstance(layer, AdjustmentLayer):
                base_u8 = to_uint8(cb * 255.0)
                adj = ensure_ndarray(layer.func(base_u8)).astype(np.float32) / 255.0
                if adj.shape[:2] != (h, w):
                    raise ImgToolkitError("adjustment changed image size")
                m = np.full((h, w), layer.opacity, np.float32)
                mask = layer._mask_for((h, w))
                if mask is not None:
                    m = m * mask
                m3 = m[..., None]
                cb = (cb * (1.0 - m3) + adj[..., :3] * m3).astype(np.float32)

        if keep_alpha:
            out = np.dstack([to_uint8(cb * 255.0), to_uint8(ab * 255.0)])
            return np.ascontiguousarray(out)

        # Composite over background (default black) to a flat RGB.
        if self.background is not None:
            bg = np.array(self.background, np.float32) / 255.0
        else:
            bg = np.zeros(3, np.float32)
        flat = cb * ab[..., None] + bg * (1.0 - ab[..., None])
        return to_uint8(flat * 255.0)

    def __len__(self):
        return len(self.layers)
