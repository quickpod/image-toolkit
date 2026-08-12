"""Batch pipeline runner and convenience batch operations.

A pipeline is a list of ``(op_name, kwargs)`` steps, each an ndarray->ndarray
transform drawn from the toolkit. :func:`batch_apply` runs the pipeline over
many inputs and writes deterministically-named outputs.
"""

from __future__ import annotations

import os

import numpy as np

from . import color, effects_advanced, filters, io_util, metadata, retouch, transform, watermark
from .errors import ImgToolkitError

# Registry of array->array operations usable in a pipeline. Extend freely; the
# GUI can introspect this to build a menu.
OPS = {
    # transform
    "resize": transform.resize,
    "crop": transform.crop,
    "rotate": transform.rotate,
    "flip": transform.flip,
    "straighten": transform.straighten,
    "canvas_resize": transform.canvas_resize,
    # color
    "brightness": color.brightness,
    "contrast": color.contrast,
    "exposure": color.exposure,
    "saturation": color.saturation,
    "vibrance": color.vibrance,
    "hue_shift": color.hue_shift,
    "white_balance": color.white_balance,
    "levels": color.levels,
    "curves": color.curves,
    "grayscale": color.grayscale,
    "invert": color.invert,
    "sepia": color.sepia,
    "auto_enhance": color.auto_enhance,
    # filters
    "gaussian_blur": filters.gaussian_blur,
    "motion_blur": filters.motion_blur,
    "sharpen": filters.sharpen,
    "vignette": filters.vignette,
    "vintage": filters.vintage,
    "pencil_sketch": filters.pencil_sketch,
    "stylize": filters.stylize,
    "hdr_effect": filters.hdr_effect,
    "apply_lut": filters.apply_lut,
    # retouch
    "denoise": retouch.denoise,
    "reduce_noise": retouch.reduce_noise,
    "skin_smooth": retouch.skin_smooth,
    "object_removal": retouch.object_removal,
    # watermark
    "text_watermark": watermark.text_watermark,
    "image_watermark": watermark.image_watermark,
    # advanced
    "content_aware_scale": effects_advanced.content_aware_scale,
}


def _naming(pattern, index, stem, ext):
    """Format an output filename from a pattern with {index}/{name}/{ext}.

    ``ext`` keeps its leading dot (e.g. ``.png``) so ``{name}{ext}`` works.
    """
    return pattern.format(index=index, i=index, name=stem, stem=stem, ext=ext)


def batch_apply(inputs, out_dir, ops, naming="{name}{ext}",
                out_format=None, quality=None) -> list:
    """Run a pipeline of ``ops`` over ``inputs`` and write to ``out_dir``.

    * ``inputs``: list of input file paths.
    * ``ops``: list of ``(op_name, kwargs)`` where ``op_name`` is a key of
      :data:`OPS`.
    * ``naming``: output filename pattern with ``{index}``/``{name}``/``{ext}``
      placeholders (``{name}`` = input stem). Deterministic.
    * ``out_format``: force an output extension (e.g. 'jpg'); else keep input's.

    Returns the list of written paths. Raises :class:`ImgToolkitError` on the
    first failing input (message names the file).
    """
    os.makedirs(out_dir, exist_ok=True)
    for name, _ in ops:
        if name not in OPS:
            raise ImgToolkitError(
                f"Unknown op '{name}'. Available: {sorted(OPS)}"
            )

    written = []
    for index, path in enumerate(inputs):
        try:
            img = io_util.load(path)
            for name, kwargs in ops:
                img = OPS[name](img, **(kwargs or {}))
        except ImgToolkitError:
            raise
        except Exception as exc:
            raise ImgToolkitError(f"batch op failed on {path}: {exc}")

        stem = os.path.splitext(os.path.basename(path))[0]
        in_ext = os.path.splitext(path)[1] or ".png"
        ext = ("." + out_format.lstrip(".")) if out_format else in_ext
        out_name = _naming(naming, index, stem, ext)
        if not os.path.splitext(out_name)[1]:
            out_name += ext
        out_path = os.path.join(out_dir, out_name)
        io_util.save(img, out_path, quality=quality)
        written.append(out_path)
    return written


def batch_resize(inputs, out_dir, width=None, height=None, keep_aspect=True,
                 out_format=None, quality=None, naming="{name}{ext}") -> list:
    """Resize every input. See :func:`imgtoolkit.transform.resize`."""
    ops = [("resize", {"width": width, "height": height,
                       "keep_aspect": keep_aspect})]
    return batch_apply(inputs, out_dir, ops, naming=naming,
                       out_format=out_format, quality=quality)


def batch_convert(inputs, out_dir, out_format, quality=None,
                  naming="{name}{ext}") -> list:
    """Convert every input to ``out_format`` (e.g. 'webp')."""
    return batch_apply(inputs, out_dir, [], naming=naming,
                       out_format=out_format, quality=quality)


def batch_watermark(inputs, out_dir, text=None, overlay_path=None,
                    out_format=None, quality=None, naming="{name}{ext}",
                    **wm_kwargs) -> list:
    """Watermark every input with ``text`` or an ``overlay_path`` image."""
    if text is not None:
        ops = [("text_watermark", {"text": text, **wm_kwargs})]
    elif overlay_path is not None:
        ops = [("image_watermark", {"overlay_path": overlay_path, **wm_kwargs})]
    else:
        raise ImgToolkitError("batch_watermark needs text or overlay_path")
    return batch_apply(inputs, out_dir, ops, naming=naming,
                       out_format=out_format, quality=quality)


def batch_strip_metadata(inputs, out_dir, naming="{name}{ext}") -> list:
    """Strip EXIF from every input (operates on the files directly)."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for index, path in enumerate(inputs):
        stem = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1] or ".png"
        out_name = _naming(naming, index, stem, ext)
        if not os.path.splitext(out_name)[1]:
            out_name += ext
        out_path = os.path.join(out_dir, out_name)
        metadata.strip_metadata(path, out_path)
        written.append(out_path)
    return written


def batch_rename(inputs, out_dir, pattern="{name}_{index}{ext}",
                 start=0) -> list:
    """Copy inputs into ``out_dir`` renamed by ``pattern`` (no pixel changes).

    ``pattern`` placeholders: ``{index}`` (starting at ``start``), ``{name}``
    (original stem), ``{ext}``. Deterministic ordering follows ``inputs``.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for offset, path in enumerate(inputs):
        index = start + offset
        stem = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1] or ".png"
        out_name = _naming(pattern, index, stem, ext)
        if not os.path.splitext(out_name)[1]:
            out_name += ext
        out_path = os.path.join(out_dir, out_name)
        img = io_util.load(path)
        io_util.save(img, out_path)
        written.append(out_path)
    return written
