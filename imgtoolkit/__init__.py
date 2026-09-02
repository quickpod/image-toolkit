"""imgtoolkit -- an open-source, headless image-editing toolkit.

Apache-2.0. Built on permissive / weak-copyleft libraries only (Pillow,
numpy, OpenCV, scikit-image, rawpy, piexif). No deep-learning model weights.

The package is organised into feature modules. Import the module you need::

    from imgtoolkit import io_util, color, filters
    img = io_util.load("photo.jpg")
    img = color.auto_enhance(img)
    io_util.save(img, "out.jpg", quality=90)

Every operation takes/returns numpy ``uint8`` arrays in RGB or RGBA order (or
explicit file paths) and raises :class:`imgtoolkit.errors.ImgToolkitError` on
failure. See ``imgtoolkit/README-API.md`` for the full API reference.
"""

from __future__ import annotations

from . import (annotate, batch, color, effects_advanced, errors, export,
               filters, history, io_util, layers, metadata, retouch,
               transform, watermark)
from .errors import DependencyError, ImgToolkitError, UnsupportedFormatError
from .history import History
from .io_util import load, save
from .layers import (AdjustmentLayer, BLEND_MODES, Document, ImageLayer,
                     Layer, blend)

__version__ = "1.0.7"

__all__ = [
    "__version__",
    # modules
    "io_util", "transform", "color", "filters", "retouch",
    "effects_advanced", "annotate", "watermark", "metadata", "export",
    "batch", "history", "layers", "errors",
    # common names
    "load", "save",
    "ImgToolkitError", "UnsupportedFormatError", "DependencyError",
    "History",
    "Document", "Layer", "ImageLayer", "AdjustmentLayer", "blend",
    "BLEND_MODES",
]
