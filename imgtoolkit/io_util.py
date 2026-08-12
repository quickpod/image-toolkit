"""Image loading and saving.

Images are always returned as ``uint8`` numpy arrays in **RGB** or **RGBA**
channel order (alpha preserved when present). RAW photos are loaded through
``rawpy`` when available; everything else goes through Pillow (with an
OpenCV fallback).
"""

from __future__ import annotations

import io
import os

import numpy as np
from PIL import Image

from ._util import ensure_ndarray, has_alpha, to_uint8
from .errors import DependencyError, ImgToolkitError, UnsupportedFormatError

# rawpy is optional: guard the import so a missing wheel never breaks the
# rest of the toolkit or the test run (RAW tests skip gracefully instead).
try:
    import rawpy  # noqa: F401

    RAWPY_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the machine
    rawpy = None
    RAWPY_AVAILABLE = False

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2",
    ".orf", ".pef", ".srw", ".raw", ".3fr", ".mef", ".mrw",
}

# Extensions Pillow handles well for our purposes.
PILLOW_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".jpe", ".webp", ".tif", ".tiff",
    ".bmp", ".gif", ".ppm", ".pgm",
}


def _ext(path: str) -> str:
    return os.path.splitext(str(path))[1].lower()


def is_raw_path(path: str) -> bool:
    """True if ``path``'s extension is a known camera-RAW type."""
    return _ext(path) in RAW_EXTENSIONS


def load(path: str) -> np.ndarray:
    """Load an image from ``path`` into an RGB/RGBA ``uint8`` ndarray.

    RAW files (``.cr2``, ``.nef``, ``.arw``, ``.dng``, ...) are demosaiced
    with rawpy when it is installed; all other formats (PNG/JPEG/WebP/TIFF/
    BMP/...) load through Pillow. Alpha is preserved.

    Raises :class:`ImgToolkitError` if the file cannot be read.
    """
    path = str(path)
    if not os.path.isfile(path):
        raise ImgToolkitError(f"File not found: {path}")

    if is_raw_path(path):
        return _load_raw(path)

    try:
        with Image.open(path) as im:
            im.load()
            arr = _pil_to_array(im)
        return arr
    except UnsupportedFormatError:
        raise
    except Exception as exc:
        # Last-ditch fallback through OpenCV for exotic files.
        try:
            import cv2

            data = np.fromfile(path, dtype=np.uint8)
            bgr = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if bgr is None:
                raise ValueError("cv2 could not decode")
            return _cv_to_rgb(bgr)
        except Exception:
            raise ImgToolkitError(f"Failed to load image {path}: {exc}")


def _pil_to_array(im: Image.Image) -> np.ndarray:
    """Convert a PIL image to an RGB/RGBA uint8 ndarray."""
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
    elif im.mode == "RGB":
        pass
    elif im.mode in ("I;16", "I", "F"):
        # High bit-depth grayscale -> normalise to 8-bit.
        a = np.asarray(im).astype(np.float64)
        if a.max() > 0:
            a = a / a.max() * 255.0
        return np.repeat(a.astype(np.uint8)[:, :, None], 3, axis=2)
    else:
        im = im.convert("RGB")
    return np.ascontiguousarray(np.asarray(im, dtype=np.uint8))


def _cv_to_rgb(bgr: np.ndarray) -> np.ndarray:
    import cv2

    if bgr.dtype != np.uint8:
        bgr = to_uint8(bgr.astype(np.float32) / max(1, bgr.max()) * 255.0)
    if bgr.ndim == 2:
        return np.repeat(bgr[:, :, None], 3, axis=2)
    if bgr.shape[2] == 4:
        return cv2.cvtColor(bgr, cv2.COLOR_BGRA2RGBA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _load_raw(path: str) -> np.ndarray:
    if not RAWPY_AVAILABLE:
        raise DependencyError(
            f"Cannot load RAW file {path}: rawpy is not installed. "
            "Install rawpy (LibRaw) to enable RAW support."
        )
    try:
        with rawpy.imread(path) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=False,
                output_bps=8,
            )
        return np.ascontiguousarray(rgb.astype(np.uint8))
    except Exception as exc:
        raise ImgToolkitError(f"Failed to load RAW image {path}: {exc}")


def save(
    img: np.ndarray,
    path: str,
    quality: int | None = None,
    strip_metadata: bool = False,
) -> str:
    """Save ``img`` (RGB/RGBA uint8 ndarray) to ``path``.

    The output format is inferred from the extension. ``quality`` (1..100)
    applies to lossy formats (JPEG/WebP). When ``strip_metadata`` is True no
    EXIF/ICC is written (Pillow already writes minimal metadata by default,
    so this mainly guards against carrying a supplied ``exif`` blob).

    Returns the path written. Raises :class:`ImgToolkitError` on failure.
    """
    img = to_uint8(ensure_ndarray(img))
    path = str(path)
    ext = _ext(path)

    if ext in RAW_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Writing RAW files is not supported (path: {path}). "
            "Choose a standard output format such as .png/.jpg/.tiff."
        )

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

    try:
        im = _array_to_pil(img, ext)
        params = {}
        if ext in (".jpg", ".jpeg", ".jpe"):
            params["quality"] = int(quality) if quality is not None else 92
            params["subsampling"] = 0 if params["quality"] >= 90 else 2
        elif ext == ".webp":
            if quality is not None:
                params["quality"] = int(quality)
            else:
                params["quality"] = 90
        elif ext in (".tif", ".tiff"):
            params["compression"] = "tiff_lzw"
        # strip_metadata: simply do not pass any exif/icc; nothing to add here.
        im.save(path, **params)
        return path
    except UnsupportedFormatError:
        raise
    except Exception as exc:
        raise ImgToolkitError(f"Failed to save image {path}: {exc}")


def _array_to_pil(img: np.ndarray, ext: str) -> Image.Image:
    """Build a PIL image, downgrading alpha for formats that lack it."""
    if img.ndim == 2:
        return Image.fromarray(img)  # inferred "L"
    if img.shape[2] == 1:
        return Image.fromarray(img[:, :, 0])
    if img.shape[2] == 4:
        if ext in (".jpg", ".jpeg", ".jpe", ".bmp"):
            # These formats have no alpha: composite onto white.
            rgb = img[:, :, :3].astype(np.float32)
            a = img[:, :, 3:4].astype(np.float32) / 255.0
            flat = rgb * a + 255.0 * (1.0 - a)
            return Image.fromarray(to_uint8(flat))  # inferred "RGB"
        return Image.fromarray(img)  # inferred "RGBA"
    return Image.fromarray(img)  # inferred "RGB"


def encode(img: np.ndarray, fmt: str, quality: int | None = None) -> bytes:
    """Encode ``img`` to an in-memory bytes blob in ``fmt`` (e.g. 'PNG')."""
    img = to_uint8(ensure_ndarray(img))
    ext = "." + fmt.lower().lstrip(".")
    buf = io.BytesIO()
    im = _array_to_pil(img, ext)
    save_fmt = {"jpg": "JPEG", "jpeg": "JPEG", "tif": "TIFF"}.get(
        fmt.lower(), fmt.upper()
    )
    kw = {}
    if save_fmt == "JPEG" and quality is not None:
        kw["quality"] = int(quality)
    im.save(buf, format=save_fmt, **kw)
    return buf.getvalue()


def image_info(path: str) -> dict:
    """Return basic info (width, height, mode, format) without full decode."""
    path = str(path)
    if is_raw_path(path):
        arr = load(path)
        h, w = arr.shape[:2]
        return {"width": w, "height": h, "channels": arr.shape[2] if arr.ndim == 3 else 1,
                "format": "RAW", "has_alpha": has_alpha(arr)}
    try:
        with Image.open(path) as im:
            return {
                "width": im.width,
                "height": im.height,
                "mode": im.mode,
                "format": im.format,
                "has_alpha": im.mode in ("RGBA", "LA", "PA"),
            }
    except Exception as exc:
        raise ImgToolkitError(f"Failed to read image info {path}: {exc}")
