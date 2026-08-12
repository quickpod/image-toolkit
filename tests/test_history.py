import numpy as np
import pytest

from imgtoolkit.history import History
from imgtoolkit.errors import ImgToolkitError


def img(v):
    return np.full((4, 4, 3), v, np.uint8)


def test_undo_redo():
    h = History()
    h.push(img(0))
    h.push(img(1))
    h.push(img(2))
    assert np.all(h.current() == 2)
    assert np.all(h.undo() == 1)
    assert np.all(h.undo() == 0)
    assert np.all(h.redo() == 1)


def test_push_truncates_redo():
    h = History()
    h.push(img(0))
    h.push(img(1))
    h.undo()
    h.push(img(9))  # new branch drops the old redo
    assert not h.can_redo()
    assert np.all(h.current() == 9)


def test_undo_underflow():
    h = History()
    h.push(img(0))
    with pytest.raises(ImgToolkitError):
        h.undo()


def test_depth_cap():
    h = History(max_depth=3)
    for i in range(6):
        h.push(img(i))
    assert len(h) == 3
    assert np.all(h.current() == 5)


def test_isolation_from_mutation():
    h = History()
    a = img(5)
    h.push(a)
    a[:] = 99  # mutate after push
    assert np.all(h.current() == 5)  # stored copy unaffected


def test_empty_current():
    with pytest.raises(ImgToolkitError):
        History().current()
