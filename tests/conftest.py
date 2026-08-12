"""Shared pytest fixtures: deterministic synthetic images."""

from __future__ import annotations

import numpy as np
import pytest


def make_gradient(h=64, w=96, seed=0):
    """A colourful gradient with a bit of structure (deterministic)."""
    ys = np.linspace(0, 255, h, dtype=np.float32)[:, None]
    xs = np.linspace(0, 255, w, dtype=np.float32)[None, :]
    r = np.broadcast_to(xs, (h, w))
    g = np.broadcast_to(ys, (h, w))
    b = (xs * 0.5 + ys * 0.5)
    img = np.stack([r, g, b], axis=2)
    # add a bright rectangle for structure
    img[h // 4:h // 2, w // 4:w // 2] = [240, 40, 40]
    return np.clip(img, 0, 255).astype(np.uint8)


def make_rgba(h=64, w=96):
    rgb = make_gradient(h, w)
    alpha = np.linspace(0, 255, w, dtype=np.uint8)[None, :].repeat(h, axis=0)
    return np.dstack([rgb, alpha])


@pytest.fixture
def gradient():
    return make_gradient()


@pytest.fixture
def rgba():
    return make_rgba()


@pytest.fixture
def small_gradient():
    return make_gradient(24, 40)


@pytest.fixture
def noisy(gradient):
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 25, gradient.shape).astype(np.float32)
    return np.clip(gradient.astype(np.float32) + noise, 0, 255).astype(np.uint8)


@pytest.fixture
def exposure_trio():
    """Three synthetic exposures of the same scene (dark/mid/bright)."""
    base = make_gradient(48, 64).astype(np.float32)
    dark = np.clip(base * 0.4, 0, 255).astype(np.uint8)
    mid = np.clip(base * 0.9, 0, 255).astype(np.uint8)
    bright = np.clip(base * 1.8, 0, 255).astype(np.uint8)
    return [dark, mid, bright]


@pytest.fixture
def stitch_pair():
    """Two horizontally-overlapping crops of a richly-textured scene."""
    rng = np.random.default_rng(7)
    H, W = 200, 400
    scene = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    # add some large blobs/edges so feature matching has something to grip
    scene = np.asarray(scene, dtype=np.uint8)
    left = scene[:, 0:250].copy()
    right = scene[:, 150:400].copy()
    return [left, right]
