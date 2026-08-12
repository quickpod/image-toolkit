"""Error types for imgtoolkit.

Every public function in :mod:`imgtoolkit` raises :class:`ImgToolkitError`
(or a subclass) on failure, so callers only ever need to catch one type.
"""


class ImgToolkitError(Exception):
    """Base error raised by all imgtoolkit operations.

    The CLI catches this and prints a clean message with a non-zero exit
    code (no traceback). Library code should wrap lower-level exceptions
    (from Pillow, OpenCV, numpy, rawpy, ...) in this type.
    """


class UnsupportedFormatError(ImgToolkitError):
    """Raised when a file extension / format cannot be read or written."""


class DependencyError(ImgToolkitError):
    """Raised when an optional dependency (e.g. rawpy) is unavailable."""
