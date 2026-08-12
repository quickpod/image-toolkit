"""EXIF metadata: read, strip, and write, via piexif + Pillow.

EXIF is a JPEG/TIFF concept; PNG/WebP have limited support. Functions raise
:class:`ImgToolkitError` on failure and degrade gracefully when a format
carries no EXIF.
"""

from __future__ import annotations

import os

import piexif
from PIL import Image

from .errors import ImgToolkitError

# Human-friendly field name -> (ifd, piexif tag).
_FIELD_MAP = {
    "Make": ("0th", piexif.ImageIFD.Make),
    "Model": ("0th", piexif.ImageIFD.Model),
    "Software": ("0th", piexif.ImageIFD.Software),
    "Artist": ("0th", piexif.ImageIFD.Artist),
    "Copyright": ("0th", piexif.ImageIFD.Copyright),
    "ImageDescription": ("0th", piexif.ImageIFD.ImageDescription),
    "DateTime": ("0th", piexif.ImageIFD.DateTime),
    "DateTimeOriginal": ("Exif", piexif.ExifIFD.DateTimeOriginal),
    "UserComment": ("Exif", piexif.ExifIFD.UserComment),
}


def read_exif(path: str) -> dict:
    """Read EXIF into a flat ``{tag_name: value}`` dict.

    Returns an empty dict if the image has no EXIF. Rational values are kept
    as piexif tuples; byte strings are decoded to str where safe.
    """
    path = str(path)
    if not os.path.isfile(path):
        raise ImgToolkitError(f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".jpe", ".tif", ".tiff"):
        # EXIF is a JPEG/TIFF concept; other formats carry none we can read.
        return {}
    try:
        exif = piexif.load(path)
    except Exception as exc:
        raise ImgToolkitError(f"Failed to read EXIF from {path}: {exc}")

    out = {}
    for ifd_name in ("0th", "Exif", "GPS", "1st"):
        ifd = exif.get(ifd_name) or {}
        for tag, value in ifd.items():
            name = piexif.TAGS[ifd_name].get(tag, {}).get("name", str(tag))
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", "replace").rstrip("\x00")
                except Exception:
                    pass
            out[name] = value
    return out


def strip_metadata(in_path: str, out_path: str) -> str:
    """Write ``in_path`` to ``out_path`` with all EXIF removed.

    For JPEG/TIFF this uses ``piexif.remove``; for other formats the pixels
    are re-encoded without an EXIF block. Returns ``out_path``.
    """
    in_path, out_path = str(in_path), str(out_path)
    if not os.path.isfile(in_path):
        raise ImgToolkitError(f"File not found: {in_path}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    ext = os.path.splitext(out_path)[1].lower()
    try:
        with Image.open(in_path) as im:
            im.load()
            data = list(im.getdata())
            clean = Image.new(im.mode, im.size)
            clean.putdata(data)
            # Re-encode with no exif/icc.
            save_kwargs = {}
            if ext in (".jpg", ".jpeg"):
                save_kwargs["quality"] = 95
            clean.save(out_path, **save_kwargs)
        # For JPEG, ensure any residual APP1 is gone.
        if ext in (".jpg", ".jpeg"):
            try:
                piexif.remove(out_path)
            except Exception:
                pass
        return out_path
    except Exception as exc:
        raise ImgToolkitError(f"Failed to strip metadata: {exc}")


def set_exif(in_path: str, out_path: str, fields: dict) -> str:
    """Write EXIF ``fields`` (by friendly name) into ``out_path``.

    Only JPEG/TIFF reliably store EXIF. Recognised field names are in
    :data:`_FIELD_MAP` (Make, Model, Software, Artist, Copyright,
    DateTimeOriginal, UserComment, ...). Returns ``out_path``.
    """
    in_path, out_path = str(in_path), str(out_path)
    if not os.path.isfile(in_path):
        raise ImgToolkitError(f"File not found: {in_path}")
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".tif", ".tiff"):
        raise ImgToolkitError("set_exif only supports JPEG/TIFF output")

    try:
        try:
            exif_dict = piexif.load(in_path)
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}}

        for name, value in fields.items():
            if name not in _FIELD_MAP:
                raise ImgToolkitError(
                    f"Unknown EXIF field '{name}'. Known: {sorted(_FIELD_MAP)}"
                )
            ifd, tag = _FIELD_MAP[name]
            if isinstance(value, str):
                value = value.encode("utf-8")
            exif_dict.setdefault(ifd, {})[tag] = value

        exif_bytes = piexif.dump(exif_dict)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with Image.open(in_path) as im:
            im.save(out_path, exif=exif_bytes)
        return out_path
    except ImgToolkitError:
        raise
    except Exception as exc:
        raise ImgToolkitError(f"Failed to set EXIF: {exc}")
