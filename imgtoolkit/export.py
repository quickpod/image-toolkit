"""Export helpers and named presets.

An export bundles: optional resize, format/quality, and metadata stripping.
Presets are plain dicts so the GUI can list/extend them.
"""

from __future__ import annotations

import os

import numpy as np

from . import io_util, transform
from ._util import ensure_ndarray
from .errors import ImgToolkitError

# Named export presets. ``resize`` is (max_w, max_h) fit-inside or None.
PRESETS = {
    "web-jpeg": {"fmt": "jpg", "quality": 82, "resize": (1920, 1920),
                 "strip_metadata": True},
    "web-webp": {"fmt": "webp", "quality": 80, "resize": (1920, 1920),
                 "strip_metadata": True},
    "web-thumb": {"fmt": "jpg", "quality": 75, "resize": (400, 400),
                  "strip_metadata": True},
    "print-tiff": {"fmt": "tiff", "quality": None, "resize": None,
                   "strip_metadata": False},
    "print-jpeg": {"fmt": "jpg", "quality": 95, "resize": None,
                   "strip_metadata": False},
    "archive-png": {"fmt": "png", "quality": None, "resize": None,
                    "strip_metadata": False},
    "social-square": {"fmt": "jpg", "quality": 85, "resize": (1080, 1080),
                      "strip_metadata": True},
}


def list_presets():
    """Return the names of available export presets."""
    return sorted(PRESETS)


def export(img: np.ndarray, path: str, fmt: str | None = None,
           quality: int | None = None, strip_metadata: bool = False,
           resize=None) -> str:
    """Export ``img`` to ``path``.

    * ``fmt`` overrides the extension when given (e.g. 'webp'); otherwise the
      extension of ``path`` decides.
    * ``resize`` = ``(max_w, max_h)`` fits the image inside that box keeping
      aspect ratio; ``None`` leaves the size unchanged.
    * ``quality`` for lossy formats; ``strip_metadata`` writes no EXIF.

    Returns the path written.
    """
    ensure_ndarray(img)
    out = img
    if resize is not None:
        mw, mh = resize
        out = transform.resize(out, mw, mh, keep_aspect=True)

    if fmt is not None:
        root, _ = os.path.splitext(path)
        path = root + "." + fmt.lower().lstrip(".")

    return io_util.save(out, path, quality=quality, strip_metadata=strip_metadata)


def export_preset(img: np.ndarray, path: str, preset: str) -> str:
    """Export ``img`` using a named ``preset`` from :data:`PRESETS`.

    The output extension is forced to the preset's format. Returns the path.
    """
    if preset not in PRESETS:
        raise ImgToolkitError(
            f"Unknown preset '{preset}'. Available: {list_presets()}"
        )
    p = PRESETS[preset]
    root, _ = os.path.splitext(path)
    out_path = root + "." + p["fmt"].lstrip(".")
    return export(img, out_path, fmt=p["fmt"], quality=p["quality"],
                  strip_metadata=p["strip_metadata"], resize=p["resize"])
