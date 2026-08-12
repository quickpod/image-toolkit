"""In-memory undo/redo stack of image states.

Designed for the GUI to reuse. It stores full numpy snapshots, which is
simple and correct but memory-hungry: peak memory is roughly
``depth * H * W * channels`` bytes. For large images the GUI may prefer a
tile/patch diff strategy; this class deliberately keeps the model trivial and
caps the depth so memory stays bounded.
"""

from __future__ import annotations

import numpy as np

from .errors import ImgToolkitError


class History:
    """A bounded linear undo/redo stack.

    Usage::

        h = History(max_depth=20)
        h.push(img0)          # initial state
        h.push(img1)          # after an edit
        prev = h.undo()       # -> img0
        again = h.redo()      # -> img1

    Pushing a new state after an undo discards the redo tail (standard linear
    history semantics).
    """

    def __init__(self, max_depth: int = 25):
        if max_depth < 1:
            raise ImgToolkitError("max_depth must be >= 1")
        self.max_depth = int(max_depth)
        self._stack: list[np.ndarray] = []
        self._index = -1  # points at the current state

    def push(self, img: np.ndarray) -> None:
        """Record ``img`` as the new current state (a defensive copy is kept)."""
        if not isinstance(img, np.ndarray):
            raise ImgToolkitError("History.push expects a numpy array")
        # Drop any redo tail.
        del self._stack[self._index + 1:]
        self._stack.append(np.ascontiguousarray(img.copy()))
        # Enforce depth cap by dropping the oldest states.
        if len(self._stack) > self.max_depth:
            overflow = len(self._stack) - self.max_depth
            del self._stack[:overflow]
        self._index = len(self._stack) - 1

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._stack) - 1

    def undo(self) -> np.ndarray:
        """Move back one state and return it. Raises if nothing to undo."""
        if not self.can_undo():
            raise ImgToolkitError("nothing to undo")
        self._index -= 1
        return self._stack[self._index].copy()

    def redo(self) -> np.ndarray:
        """Move forward one state and return it. Raises if nothing to redo."""
        if not self.can_redo():
            raise ImgToolkitError("nothing to redo")
        self._index += 1
        return self._stack[self._index].copy()

    def current(self) -> np.ndarray:
        """Return the current state (copy). Raises if the history is empty."""
        if self._index < 0:
            raise ImgToolkitError("history is empty")
        return self._stack[self._index].copy()

    def __len__(self) -> int:
        return len(self._stack)

    def clear(self) -> None:
        self._stack.clear()
        self._index = -1
