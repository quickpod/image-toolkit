#!/usr/bin/env python3
r"""Image Toolkit -- a pure-stdlib tkinter GUI on top of the ``imgtoolkit`` API.

A single main window: a left sidebar of tool groups (Transform, Color & Tone,
Filters & Effects, Retouch, Annotate, Layers, Batch, File), a central image
canvas that shows the working image (zoom-to-fit + zoom/pan), and a right panel
of controls for the selected tool.  A top menu and a bottom status/results bar
round it off.

Every pixel operation calls the tested ``imgtoolkit`` core library -- this file
never re-implements image logic.  Heavy operations (filters, denoise, inpaint,
RAW load, batch) run on a background daemon thread so the UI never freezes;
results are marshalled back with ``self.after`` and reported inline (the
``ImgToolkitError`` message, never a raw traceback).  Undo/redo is the core
``history.History`` of full numpy snapshots.

Design goals baked in here:
  * built on the vendored ``imgtoolkit/aura.py`` design system (the QuickOpen
    "Aura" look layered over CustomTkinter): a sidebar tool rail, the signature
    accent beam under the header, and an inline status bar.  The working image
    lives on a persistent Pillow ``ImageTk`` canvas while each tool swaps only
    its control panel.  Runtime deps: ``customtkinter`` (+ ``darkdetect``).
  * Importing this module does nothing.  Only :func:`main` builds a root window,
    and it degrades gracefully (prints a message, returns 0) with no display.
  * Frozen-exe safe: bundled assets are resolved via ``sys._MEIPASS`` / the exe
    directory when ``sys.frozen`` is set -- never ``__file__``.

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

import os
import sys
import threading

# NOTE: tkinter / numpy / Pillow are imported lazily inside build_app()/main()
# so that merely importing this module (packaging, headless CI) never fails.

APP_NAME = "Image Toolkit"
APP_VERSION = "1.0.0"
WINDOW_TITLE = "Image Toolkit — by QuickOpen (quickopen.ai)"
PROJECT_URL = "https://quickopen.ai"

# File-dialog filters (the core loads all of these; RAW via rawpy when present).
IMAGE_TYPES = [
    ("Images", "*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp *.gif"),
    ("RAW photos", "*.cr2 *.cr3 *.nef *.arw *.dng *.raf *.rw2 *.orf *.pef *.srw"),
    ("All files", "*.*"),
]
SAVE_TYPES = [
    ("PNG", "*.png"), ("JPEG", "*.jpg"), ("WebP", "*.webp"),
    ("TIFF", "*.tiff"), ("BMP", "*.bmp"), ("All files", "*.*"),
]
CUBE_TYPES = [("Adobe .cube LUT", "*.cube"), ("All files", "*.*")]

WM_POSITIONS = [
    "top-left", "top", "top-right", "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
]
ANCHORS = [
    "top-left", "top", "top-right", "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
]
RESAMPLE = ["auto", "nearest", "bilinear", "bicubic", "area", "lanczos"]

# Per-app Aura accent — Image Toolkit's icon teal (publish icon set).
ACCENT = "#0e8c7f"

# (category, [(tool_id, label), ...]) -- tool_id maps to a _panel_<id> method.
TOOL_TREE = [
    ("Transform", [
        ("crop", "Crop"),
        ("rotate", "Rotate"),
        ("straighten", "Straighten"),
        ("flip", "Flip"),
        ("resize", "Resize"),
        ("canvas", "Canvas size"),
        ("perspective", "Perspective"),
    ]),
    ("Color & Tone", [
        ("light", "Light"),
        ("tonemask", "Highlights & shadows"),
        ("saturation", "Saturation & hue"),
        ("whitebalance", "White balance"),
        ("levels", "Levels"),
        ("curves", "Curves"),
        ("colorbalance", "Color balance"),
        ("quickcolor", "Auto / grayscale / invert / sepia"),
    ]),
    ("Filters & Effects", [
        ("blur", "Blur"),
        ("sharpenf", "Sharpen / unsharp"),
        ("vignette", "Vignette"),
        ("effects", "Artistic effects"),
        ("lut", "3D LUT (.cube)"),
    ]),
    ("Retouch", [
        ("denoise", "Denoise"),
        ("skin", "Skin smooth"),
        ("redeye", "Red-eye"),
        ("heal", "Heal / remove object"),
    ]),
    ("Annotate", [
        ("draw", "Shapes & brush"),
        ("text", "Text"),
    ]),
    ("Layers", [
        ("layers", "Layers"),
    ]),
    ("Batch", [
        ("batch", "Batch process"),
    ]),
    ("File", [
        ("export", "Export / presets"),
    ]),
]

TOOL_DESCRIPTIONS = {
    "crop": "Drag a rectangle on the image, then crop to it.",
    "rotate": "Rotate 90°/180° or by an arbitrary angle (canvas expands).",
    "straighten": "Level a tilted horizon; keeps the original frame size.",
    "flip": "Mirror horizontally or vertically.",
    "resize": "Scale to new pixel dimensions, optionally keeping aspect.",
    "canvas": "Change the canvas size without scaling (pad or crop by anchor).",
    "perspective": "Place 4 corners (TL, TR, BR, BL) to correct perspective.",
    "light": "Brightness, contrast and exposure — live preview, then apply.",
    "tonemask": "Recover highlights and lift shadows (luminance-masked).",
    "saturation": "Saturation, vibrance and hue rotation.",
    "whitebalance": "Auto gray-world balance, or manual temperature / tint.",
    "levels": "Photoshop-style input/gamma/output levels.",
    "curves": "Draggable tone curve — double-click to add points.",
    "colorbalance": "Per-tonal-range RGB colour offsets.",
    "quickcolor": "One-click auto-enhance, grayscale, invert or sepia.",
    "blur": "Gaussian, motion or lens (bokeh) blur.",
    "sharpenf": "Unsharp-mask sharpening.",
    "vignette": "Darken (or shape) the edges.",
    "effects": "HDR look, vintage/film, pencil, stylize, oil, cartoon.",
    "lut": "Apply an Adobe .cube 3-D colour LUT.",
    "denoise": "Non-local-means denoise.",
    "skin": "Edge-preserving skin smoothing.",
    "redeye": "Drag over an eye to remove red-eye.",
    "heal": "Paint a mask, then heal / remove an object (classical inpaint).",
    "draw": "Brush, line, arrow, rectangle, ellipse or highlighter.",
    "text": "Add a text label at a point you click.",
    "layers": "Non-destructive layer compositing (blend modes, opacity, masks).",
    "batch": "Run resize / convert / watermark / strip-metadata over many files.",
    "export": "Export with a named preset or custom format & quality.",
}

# Aura sidebar nav glyphs — chosen from the DejaVu-safe set (Linux fallback
# font): ⌂ ⚙ ⇄ ⚲ ▤ ◉ ✎ ◈ ⊙ ℹ ✳ .  One glyph per tool category.
_CAT_GLYPH = {
    "Transform": "⇄", "Color & Tone": "◉", "Filters & Effects": "✳",
    "Retouch": "✎", "Annotate": "◈", "Layers": "▤", "Batch": "⊙",
    "File": "⚙",
}
GLYPHS = {tid: _CAT_GLYPH.get(cat, "◈")
          for cat, tools in TOOL_TREE for tid, _label in tools}

# Flat (id, label) list — a stable, crawler-discoverable section index.
SECTIONS = [(tid, label) for _cat, tools in TOOL_TREE for tid, label in tools]
FIRST_TOOL = SECTIONS[0][0]


# ---------------------------------------------------------------------------
# Asset / frozen handling
# ---------------------------------------------------------------------------
def asset_path(name):
    """Locate a bundled asset from source OR a PyInstaller one-file build.

    For a frozen exe we look only at ``sys._MEIPASS`` and the executable's own
    directory (never ``__file__``).  From source we also consult the package
    dir, the repo root and the CWD.  Returns an absolute path or ``None``.
    """
    roots = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(meipass)
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        roots += [here, os.path.dirname(here), os.getcwd()]
    for root in roots:
        candidate = os.path.join(root, name)
        if os.path.exists(candidate):
            return candidate
    return None


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def open_in_file_manager(path):
    """Best-effort 'reveal in file manager', guarded on every platform."""
    try:
        folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
        if hasattr(os, "startfile"):
            os.startfile(folder)              # noqa: S606 - intended (Windows)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", folder])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", folder])
        return True
    except Exception:
        return False


def open_with_default_app(path):
    """Open a file/URL with the OS default application, guarded."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)                # noqa: S606
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The app (built lazily; tkinter/numpy/Pillow imported only inside build_app)
# ---------------------------------------------------------------------------
def build_app():
    """Construct and return the App class bound to live tkinter/numpy/PIL.

    Kept inside a function so this module imports cleanly without a display.
    """
    import tkinter as tk
    from tkinter import ttk, filedialog, colorchooser
    from .aura import filedialog  # noqa: F811 - Aura kdialog-native pickers
    import customtkinter as ctk
    import numpy as np
    from PIL import Image, ImageTk

    from . import aura, guiconfig
    from . import (io_util, transform, color, filters, retouch, annotate,
                   watermark, export, batch, layers)
    from .errors import ImgToolkitError
    from .history import History

    FONT = aura._family()   # Aura UI family (DejaVu Sans on Linux, Segoe on NT)
    MAX_PREVIEW = 900   # longest edge of the fast live-preview proxy

    def np_to_pil(img):
        """Convert an RGB/RGBA/gray uint8 ndarray to a PIL image."""
        arr = np.asarray(img)
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        if arr.ndim == 2:
            return Image.fromarray(arr, "L")
        if arr.shape[2] == 4:
            return Image.fromarray(arr, "RGBA")
        return Image.fromarray(arr[:, :, :3], "RGB")

    # ==================================================================
    # Small reusable control widgets
    # ==================================================================
    class SliderRow(ttk.Frame):
        """Label + Scale + live value readout + reset-to-default."""

        def __init__(self, master, label, lo, hi, default, on_change=None,
                     fmt="{:.2f}", resolution=None, width=120):
            super().__init__(master, style="TFrame")
            self.lo, self.hi, self.default = lo, hi, default
            self.fmt, self.resolution = fmt, resolution
            self.on_change = on_change
            self.var = tk.DoubleVar(value=default)
            top = ttk.Frame(self, style="TFrame")
            top.pack(fill="x")
            ttk.Label(top, text=label, style="TLabel").pack(side="left")
            self.val_lbl = ttk.Label(top, text=fmt.format(default),
                                     style="Muted.TLabel")
            self.val_lbl.pack(side="right")
            ttk.Button(top, text="⟲", width=2,
                       command=self.reset).pack(side="right", padx=(0, 6))
            self.scale = ttk.Scale(self, from_=lo, to=hi, variable=self.var,
                                   orient="horizontal", command=self._changed)
            self.scale.pack(fill="x")

        def _changed(self, _=None):
            v = self.value()
            self.val_lbl.configure(text=self.fmt.format(v))
            if self.on_change:
                self.on_change(v)

        def value(self):
            v = float(self.var.get())
            if self.resolution:
                v = round(v / self.resolution) * self.resolution
            return v

        def set(self, v):
            self.var.set(v)
            self.val_lbl.configure(text=self.fmt.format(self.value()))

        def reset(self):
            self.set(self.default)
            if self.on_change:
                self.on_change(self.value())

    class LabeledEntry(ttk.Frame):
        def __init__(self, master, label, default="", width=10):
            super().__init__(master, style="TFrame")
            ttk.Label(self, text=label, width=14, anchor="w").pack(side="left")
            self.var = tk.StringVar(value=str(default))
            ttk.Entry(self, textvariable=self.var, width=width).pack(side="left")

        def get(self):
            return self.var.get().strip()

        def get_int(self, default=None):
            s = self.get()
            if not s:
                return default
            return int(float(s))

        def get_float(self, default=None):
            s = self.get()
            if not s:
                return default
            return float(s)

    class CurveEditor(ttk.Frame):
        """A tiny draggable tone-curve widget → list of (in, out) points 0..255.

        Double-click adds a point; right-click removes the nearest interior
        point; drag to move. Emits ``on_change`` (debounced by the caller).
        """

        SIZE = 220
        PAD = 12

        def __init__(self, master, app, on_change=None):
            super().__init__(master, style="TFrame")
            self.app = app
            self.on_change = on_change
            self.points = [(0.0, 0.0), (255.0, 255.0)]
            self.canvas = tk.Canvas(self, width=self.SIZE, height=self.SIZE,
                                    highlightthickness=1, bd=0)
            self.canvas.pack()
            app.track(self.canvas, "curve")
            app._curves.append(self)
            self._drag = None
            self.canvas.bind("<Button-1>", self._press)
            self.canvas.bind("<B1-Motion>", self._move)
            self.canvas.bind("<ButtonRelease-1>", self._release)
            self.canvas.bind("<Double-Button-1>", self._add)
            self.canvas.bind("<Button-3>", self._remove)
            self.after(30, self.redraw)

        def _to_px(self, ix, iy):
            s = self.SIZE - 2 * self.PAD
            return (self.PAD + ix / 255.0 * s,
                    self.PAD + (1 - iy / 255.0) * s)

        def _to_val(self, px, py):
            s = self.SIZE - 2 * self.PAD
            ix = (px - self.PAD) / s * 255.0
            iy = (1 - (py - self.PAD) / s) * 255.0
            return (min(255.0, max(0.0, ix)), min(255.0, max(0.0, iy)))

        def redraw(self):
            c = self.canvas
            c.delete("all")
            p = self.app._pal()
            c.configure(bg=p["surface"])
            s = self.SIZE - 2 * self.PAD
            for k in range(5):
                x = self.PAD + k / 4 * s
                c.create_line(x, self.PAD, x, self.PAD + s, fill=p["border"])
                c.create_line(self.PAD, x, self.PAD + s, x, fill=p["border"])
            pts = sorted(self.points)
            px = [self._to_px(a, b) for a, b in pts]
            for i in range(len(px) - 1):
                c.create_line(*px[i], *px[i + 1], fill=p["primary"], width=2)
            for a, b in pts:
                x, y = self._to_px(a, b)
                c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=p["primary"],
                              outline=p["text"])

        def _nearest(self, px, py):
            best, bd = None, 1e9
            for i, (a, b) in enumerate(self.points):
                x, y = self._to_px(a, b)
                d = (x - px) ** 2 + (y - py) ** 2
                if d < bd:
                    best, bd = i, d
            return best if bd < 200 else None

        def _press(self, e):
            self._drag = self._nearest(e.x, e.y)

        def _move(self, e):
            if self._drag is None:
                return
            ix, iy = self._to_val(e.x, e.y)
            i = self._drag
            # endpoints keep their input coordinate pinned
            if i == 0:
                ix = 0.0
            elif i == len(self.points) - 1:
                ix = 255.0
            self.points[i] = (ix, iy)
            self.redraw()

        def _release(self, _e):
            if self._drag is not None and self.on_change:
                self.on_change()
            self._drag = None

        def _add(self, e):
            ix, iy = self._to_val(e.x, e.y)
            self.points.append((ix, iy))
            self.points.sort()
            self.redraw()
            if self.on_change:
                self.on_change()

        def _remove(self, e):
            i = self._nearest(e.x, e.y)
            if i is not None and 0 < i < len(self.points) - 1:
                del self.points[i]
                self.redraw()
                if self.on_change:
                    self.on_change()

        def get_points(self):
            return [(float(a), float(b)) for a, b in sorted(self.points)]

        def reset(self):
            self.points = [(0.0, 0.0), (255.0, 255.0)]
            self.redraw()
            if self.on_change:
                self.on_change()

    class FileList(ttk.Frame):
        """Multi-file listbox with Add / Remove / Clear (for batch)."""

        def __init__(self, master, app, filetypes=None):
            super().__init__(master, style="TFrame")
            self.app = app
            self.filetypes = filetypes or IMAGE_TYPES
            box = ttk.Frame(self, style="TFrame")
            box.pack(fill="both", expand=True)
            self.listbox = tk.Listbox(box, height=7, activestyle="none",
                                      selectmode="extended", exportselection=False)
            sb = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
            self.listbox.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            self.listbox.pack(side="left", fill="both", expand=True)
            app.track(self.listbox, "listbox")
            btns = ttk.Frame(self, style="TFrame")
            btns.pack(fill="x", pady=(6, 0))
            ttk.Button(btns, text="Add files…", command=self.add,
                       style="Accent.TButton").pack(side="left")
            ttk.Button(btns, text="Remove", command=self.remove).pack(side="left", padx=4)
            ttk.Button(btns, text="Clear", command=self.clear).pack(side="left")

        def add(self):
            paths = filedialog.askopenfilenames(title="Add images",
                                                filetypes=self.filetypes)
            for p in paths:
                self.listbox.insert("end", p)

        def remove(self):
            for i in reversed(self.listbox.curselection()):
                self.listbox.delete(i)

        def clear(self):
            self.listbox.delete(0, "end")

        def items(self):
            return list(self.listbox.get(0, "end"))

    # ==================================================================
    # The image canvas: display, zoom/pan, coordinate mapping, overlays
    # ==================================================================
    class ImageCanvas(ttk.Frame):
        """Shows the working image, maps canvas<->image coords, and hosts the
        interactive tool overlays (crop rect, 4-point quad, mask brush, strokes).
        """

        def __init__(self, master, app):
            super().__init__(master, style="TFrame")
            self.app = app
            self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
            self.canvas.pack(fill="both", expand=True)
            app.track(self.canvas, "imgcanvas")

            self._img = None          # committed working ndarray (source of truth for display)
            self._preview = None      # transient preview ndarray (not committed)
            self._photo = None        # keep ImageTk ref alive
            self.scale = 1.0
            self._fit = True
            self.pan = [0.0, 0.0]

            # interaction state
            self.mode = None          # None|'rect'|'quad'|'point'|'mask'|'free'|'two'
            self._cb = None
            self._quad_n = 4
            self._pts = []            # canvas-space temp points
            self._rect0 = None
            self._mask = None         # PIL 'L' mask at image resolution
            self.brush = 30

            self.canvas.bind("<Configure>", lambda e: self._on_resize())
            self.canvas.bind("<ButtonPress-1>", self._b1_press)
            self.canvas.bind("<B1-Motion>", self._b1_move)
            self.canvas.bind("<ButtonRelease-1>", self._b1_release)
            self.canvas.bind("<ButtonPress-2>", self._pan_press)
            self.canvas.bind("<B2-Motion>", self._pan_move)
            self.canvas.bind("<ButtonPress-3>", self._pan_press)
            self.canvas.bind("<B3-Motion>", self._pan_move)
            self.canvas.bind("<MouseWheel>", self._wheel)
            self.canvas.bind("<Button-4>", lambda e: self.zoom(1.25))
            self.canvas.bind("<Button-5>", lambda e: self.zoom(0.8))

        # ---- display ---------------------------------------------------
        def set_image(self, img):
            self._img = img
            self._preview = None
            self._mask = None
            self.fit()

        def has_image(self):
            return self._img is not None

        def current(self):
            return self._preview if self._preview is not None else self._img

        def set_preview(self, img):
            self._preview = img
            self.redraw()

        def clear_preview(self):
            if self._preview is not None:
                self._preview = None
                self.redraw()

        def _dims(self):
            img = self.current()
            if img is None:
                return 0, 0
            h, w = img.shape[:2]
            return w, h

        def _origin(self):
            """Top-left of the scaled image on the canvas (with pan/centering)."""
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())
            iw, ih = self._dims()
            ox = (cw - iw * self.scale) / 2 + self.pan[0]
            oy = (ch - ih * self.scale) / 2 + self.pan[1]
            return ox, oy

        def canvas_to_image(self, cx, cy):
            ox, oy = self._origin()
            iw, ih = self._dims()
            ix = (cx - ox) / self.scale
            iy = (cy - oy) / self.scale
            return (int(round(min(max(ix, 0), iw))),
                    int(round(min(max(iy, 0), ih))))

        def image_to_canvas(self, ix, iy):
            ox, oy = self._origin()
            return ox + ix * self.scale, oy + iy * self.scale

        def fit(self):
            self._fit = True
            self.pan = [0.0, 0.0]
            self._recompute_fit()
            self.redraw()

        def _recompute_fit(self):
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())
            iw, ih = self._dims()
            if iw and ih:
                self.scale = min(cw / iw, ch / ih)
                self.scale = max(0.02, min(self.scale, 16))

        def zoom(self, factor):
            if not self.has_image():
                return
            self._fit = False
            self.scale = max(0.02, min(self.scale * factor, 32))
            self.redraw()
            self.app._update_zoom_label()

        def _on_resize(self):
            if self._fit:
                self._recompute_fit()
            self.redraw()

        def _display_pil(self):
            img = self.current()
            if img is None:
                return None
            iw, ih = self._dims()
            w = max(1, int(iw * self.scale))
            h = max(1, int(ih * self.scale))
            pil = np_to_pil(img)
            resample = Image.BILINEAR if self.scale < 3 else Image.NEAREST
            disp = pil.resize((w, h), resample)
            p = self.app._pal()
            if disp.mode == "RGBA":
                bg = Image.new("RGBA", (w, h), _hex_to_rgb(p["canvas"]) + (255,))
                disp = Image.alpha_composite(bg, disp).convert("RGB")
            elif disp.mode == "L":
                disp = disp.convert("RGB")
            # paint the mask (retouch) as a translucent red overlay
            if self.mode == "mask" and self._mask is not None:
                m = self._mask.resize((w, h), Image.NEAREST)
                red = Image.new("RGBA", (w, h), (255, 40, 40, 0))
                red.putalpha(m.point(lambda v: 120 if v else 0))
                disp = Image.alpha_composite(disp.convert("RGBA"), red).convert("RGB")
            return disp

        def redraw(self):
            self.canvas.delete("all")
            p = self.app._pal()
            self.canvas.configure(bg=p["canvas"])
            disp = self._display_pil()
            if disp is None:
                self.canvas.create_text(
                    self.canvas.winfo_width() // 2 or 200,
                    self.canvas.winfo_height() // 2 or 150,
                    text="Open an image to begin  (File ▸ Open)",
                    fill=p["muted"], font=(FONT, 12))
                return
            ox, oy = self._origin()
            self._photo = ImageTk.PhotoImage(disp)
            self.canvas.create_image(ox, oy, anchor="nw", image=self._photo)
            self._draw_overlay()

        def _draw_overlay(self):
            p = self.app._pal()
            col = p["overlay"]
            if self.mode == "quad" and self._pts:
                cpts = [self.image_to_canvas(*q) for q in self._pts]
                for (x, y) in cpts:
                    self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5,
                                            outline=col, width=2)
                if len(cpts) > 1:
                    flat = [v for xy in cpts for v in xy]
                    self.canvas.create_line(*flat, fill=col, width=2)
            if self.mode == "two" and len(self._pts) == 1:
                pass  # rubber-band drawn during motion

        # ---- interaction arming ---------------------------------------
        def arm_rect(self, cb):
            self._reset_interaction("rect", cb)

        def arm_quad(self, n, cb):
            self._quad_n = n
            self._reset_interaction("quad", cb)

        def arm_point(self, cb):
            self._reset_interaction("point", cb)

        def arm_two(self, cb):
            self._reset_interaction("two", cb)

        def arm_free(self, cb):
            self._reset_interaction("free", cb)

        def arm_mask(self):
            self._reset_interaction("mask", None)
            iw, ih = self._dims()
            self._mask = Image.new("L", (iw, ih), 0)
            self.redraw()

        def clear_mask(self):
            if self._mask is not None:
                iw, ih = self._dims()
                self._mask = Image.new("L", (iw, ih), 0)
                self.redraw()

        def mask_array(self):
            if self._mask is None:
                return None
            return np.array(self._mask)

        def disarm(self):
            self.mode = None
            self._cb = None
            self._pts = []
            self._rect0 = None
            self.redraw()

        def _reset_interaction(self, mode, cb):
            self.mode = mode
            self._cb = cb
            self._pts = []
            self._rect0 = None
            self.redraw()

        # ---- mouse events ---------------------------------------------
        def _b1_press(self, e):
            if not self.has_image():
                return
            if self.mode == "rect":
                self._rect0 = (e.x, e.y)
            elif self.mode == "mask":
                self._paint(e.x, e.y)
            elif self.mode == "free":
                self._pts = [self.canvas_to_image(e.x, e.y)]
            elif self.mode == "point":
                pt = self.canvas_to_image(e.x, e.y)
                cb = self._cb
                self.disarm()
                if cb:
                    cb(pt)
            elif self.mode in ("quad", "two"):
                self._pts.append(self.canvas_to_image(e.x, e.y))
                self.redraw()
                target = self._quad_n if self.mode == "quad" else 2
                if len(self._pts) >= target:
                    pts, cb = list(self._pts), self._cb
                    self.disarm()
                    if cb:
                        cb(pts)

        def _b1_move(self, e):
            if self.mode == "rect" and self._rect0:
                self.redraw()
                x0, y0 = self._rect0
                self.canvas.create_rectangle(x0, y0, e.x, e.y,
                                             outline=self.app._pal()["overlay"],
                                             width=2, dash=(4, 3))
            elif self.mode == "mask":
                self._paint(e.x, e.y)
            elif self.mode == "free":
                self._pts.append(self.canvas_to_image(e.x, e.y))
                self.redraw()
                self._draw_free_preview()
            elif self.mode == "two" and len(self._pts) == 1:
                self.redraw()
                x0, y0 = self.image_to_canvas(*self._pts[0])
                self.canvas.create_line(x0, y0, e.x, e.y,
                                        fill=self.app._pal()["overlay"], width=2)

        def _b1_release(self, e):
            if self.mode == "rect" and self._rect0:
                p0 = self.canvas_to_image(*self._rect0)
                p1 = self.canvas_to_image(e.x, e.y)
                box = (min(p0[0], p1[0]), min(p0[1], p1[1]),
                       max(p0[0], p1[0]), max(p0[1], p1[1]))
                cb = self._cb
                self.disarm()
                if cb and box[2] > box[0] and box[3] > box[1]:
                    cb(box)
            elif self.mode == "free":
                pts, cb = list(self._pts), self._cb
                self.disarm()
                if cb and len(pts) >= 1:
                    cb(pts)

        def _draw_free_preview(self):
            if len(self._pts) < 2:
                return
            cpts = [self.image_to_canvas(*q) for q in self._pts]
            flat = [v for xy in cpts for v in xy]
            self.canvas.create_line(*flat, fill=self.app._pal()["overlay"],
                                    width=2, capstyle="round")

        def _paint(self, cx, cy):
            if self._mask is None:
                return
            ix, iy = self.canvas_to_image(cx, cy)
            r = self.brush
            from PIL import ImageDraw
            d = ImageDraw.Draw(self._mask)
            d.ellipse((ix - r, iy - r, ix + r, iy + r), fill=255)
            self.redraw()

        # ---- pan / wheel ----------------------------------------------
        def _pan_press(self, e):
            self._pan_anchor = (e.x, e.y, self.pan[0], self.pan[1])

        def _pan_move(self, e):
            if not hasattr(self, "_pan_anchor"):
                return
            x0, y0, px, py = self._pan_anchor
            self._fit = False
            self.pan = [px + (e.x - x0), py + (e.y - y0)]
            self.redraw()

        def _wheel(self, e):
            self.zoom(1.25 if e.delta > 0 else 0.8)

    # ==================================================================
    # The main window
    # ==================================================================
    class App(aura.AuraApp):
        """Aura-scaffolded image editor: sidebar tool rail + persistent canvas
        + swappable per-tool control panel + inline status bar."""

        def __init__(self):
            super().__init__(
                title=WINDOW_TITLE, app_name=APP_NAME, accent=ACCENT,
                theme=guiconfig.get_theme(),
                icon_png=asset_path("image-toolkit.png"),
                version=APP_VERSION, tagline="offline editor",
                on_theme_change=guiconfig.set_theme,
                size=(1280, 820), min_size=(1060, 680))

            self.image = None            # working ndarray (source of truth)
            self.image_path = None
            self.history = History(max_depth=20)
            self._proxy = None
            self._proxy_for = None       # id() of image the proxy was built from
            self._preview_job = None
            self._busy = False
            self._app_tracked = []       # (widget, role) raw-tk recolor registry
            self._curves = []            # CurveEditor instances (theme-flip redraw)
            self._panels = {}            # sid -> holder frame (crawler-friendly)
            self._current = None         # active holder frame (crawler-friendly)
            self.doc = None              # layers Document (built on demand)

            self._extra_styles()
            self._build_content_area()
            self._build_menu()
            self._build_nav()
            self._bind_keys()
            self._set_icon()
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            self.after(60, lambda: self.show(FIRST_TOOL))

        # ---- assets / icon --------------------------------------------
        def _set_icon(self):
            try:
                ico = asset_path("image-toolkit.ico")
                if ico:
                    self.iconbitmap(ico)
                    return
            except Exception:
                pass
            try:
                png = asset_path("image-toolkit.png")
                if png:
                    img = tk.PhotoImage(file=png)
                    self._img_refs.append(img)
                    self.iconphoto(True, img)
            except Exception:
                pass  # icon is cosmetic; never block launch

        # ---- theming bridge (Aura owns the palette; adapt custom tk widgets)
        def track(self, widget, role):
            """Register a raw tk widget for re-theming when the theme flips.

            "listbox" is delegated to the Aura registry; the app-specific
            "imgcanvas"/"curve" roles are recoloured by :meth:`_recolor_custom`.
            """
            if role == "listbox":
                aura.track(widget, "listbox")
                return
            self._app_tracked.append((widget, role))
            self._recolor_custom()

        def _pal(self):
            """A house-style palette dict, resolved from the live Aura tokens,
            so the legacy ImageCanvas/CurveEditor drawing code works unchanged."""
            p = aura.P()
            return {
                "surface": p["surface"], "border": p["border"],
                "primary": p["accent"], "overlay": p["accent"],
                "text": p["text"], "muted": p["muted"],
                "canvas": p["bg"], "bg": p["bg"],
                "ok": p["ok"], "err": p["danger"], "entry": p["field"],
                "sel": p["accent"], "sel_fg": p["on_accent"],
                "trough": p["surface3"],
            }

        def _recolor_custom(self):
            p = self._pal()
            for widget, role in list(self._app_tracked):
                try:
                    if not widget.winfo_exists():
                        self._app_tracked.remove((widget, role))
                        continue
                    if role == "imgcanvas":
                        widget.configure(bg=p["canvas"], highlightthickness=0)
                    elif role == "curve":
                        widget.configure(bg=p["surface"], highlightthickness=1,
                                         highlightbackground=p["border"])
                except Exception:
                    pass

        def _extra_styles(self):
            """Define the few ttk label styles the tool panels reference that
            Aura's style_ttk does not (re-applied after every theme flip)."""
            p = aura.P()
            fam = aura._family()
            cap = aura.TOKENS["type"]["caption"]
            st = ttk.Style(self)
            st.configure("Sub.TLabel", background=p["bg"], foreground=p["muted"],
                         font=(fam, cap))
            st.configure("Status.TLabel", background=p["bg"],
                         foreground=p["muted"])
            st.configure("Brand.TLabel", background=p["bg"], foreground=p["text"],
                         font=(fam, 13, "bold"))
            st.configure("Header.TLabel", background=p["bg"],
                         foreground=p["text"], font=(fam, 15, "bold"))

        def set_theme(self, theme):
            super().set_theme(theme)
            self._extra_styles()
            self._recolor_custom()
            try:
                self.canvas.redraw()
            except Exception:
                pass
            for ce in list(self._curves):
                try:
                    ce.redraw()
                except Exception:
                    pass

        def toggle_theme(self):
            self.set_theme("light" if self.theme == "dark" else "dark")

        # ---- content: persistent canvas (left) + swappable tool panel (right)
        def _build_content_area(self):
            self._content.grid_columnconfigure(0, weight=1)
            self._content.grid_columnconfigure(1, weight=0, minsize=346)
            self._content.grid_rowconfigure(0, weight=1)

            left = ctk.CTkFrame(self._content, fg_color="transparent")
            left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
            left.grid_rowconfigure(0, weight=1)
            left.grid_columnconfigure(0, weight=1)
            self.canvas = ImageCanvas(left, self)
            self.canvas.grid(row=0, column=0, sticky="nsew")

            zoom = ctk.CTkFrame(left, fg_color="transparent")
            zoom.grid(row=1, column=0, sticky="ew", pady=(10, 0))
            aura.AuraButton(zoom, "−", kind="secondary", width=34, height=28,
                            command=lambda: self.canvas.zoom(0.8)).pack(side="left")
            aura.AuraButton(zoom, "Fit", kind="secondary", width=48, height=28,
                            command=lambda: self.canvas.fit()).pack(
                side="left", padx=5)
            aura.AuraButton(zoom, "+", kind="secondary", width=34, height=28,
                            command=lambda: self.canvas.zoom(1.25)).pack(side="left")
            self.zoom_lbl = aura.Caption(zoom, "—")
            self.zoom_lbl.pack(side="left", padx=12)
            self.size_lbl = aura.Caption(zoom, "")
            self.size_lbl.pack(side="right")
            self.hist_lbl = aura.Caption(zoom, "")
            self.hist_lbl.pack(side="right", padx=12)

            self._panelhost = ctk.CTkFrame(self._content, fg_color="transparent",
                                           width=346)
            self._panelhost.grid(row=0, column=1, sticky="nsew")
            self._panelhost.grid_propagate(False)
            self._panelhost.grid_columnconfigure(0, weight=1)
            self._panelhost.grid_rowconfigure(0, weight=1)

            # header quick actions (right of the page title)
            aura.AuraButton(self.header_actions, "Open", kind="secondary",
                            height=30, command=self.open_image).pack(side="left")
            aura.AuraButton(self.header_actions, "Save", kind="secondary",
                            height=30, command=self.save_image).pack(
                side="left", padx=(8, 0))
            aura.AuraButton(self.header_actions, "Undo", kind="ghost", height=30,
                            width=56, command=self.undo).pack(
                side="left", padx=(8, 0))
            aura.AuraButton(self.header_actions, "Redo", kind="ghost", height=30,
                            width=56, command=self.redo).pack(side="left")

        # ---- sidebar nav: one section per tool, grouped by category caption
        def _build_nav(self):
            # AuraApp's nav is a plain frame; 29 tools need a scrollable rail.
            try:
                self._nav.destroy()
            except Exception:
                pass
            self.sidebar.grid_rowconfigure(1, weight=1)
            self.sidebar.grid_rowconfigure(2, weight=0)
            self._nav = ctk.CTkScrollableFrame(self.sidebar,
                                               fg_color="transparent", width=196)
            self._nav.grid(row=1, column=0, sticky="nsew", padx=4)
            for cat, tools in TOOL_TREE:
                self._add_nav_header(cat)
                for tid, label in tools:
                    self.add_section(tid, label, GLYPHS.get(tid, "◈"),
                                     self._make_builder(tid))

        def _add_nav_header(self, text):
            aura.SectionLabel(self._nav, text).pack(
                fill="x", padx=8, pady=(12, 3), anchor="w")

        def add_section(self, sid, label, glyph="", builder=None):
            """Register a sidebar tool pill + a lazily-built scrollable panel."""
            item = aura._NavItem(self._nav, label, glyph,
                                 lambda s=sid: self.show(s))
            item.pack(fill="x", pady=1)
            holder = ctk.CTkScrollableFrame(self._panelhost,
                                            fg_color="transparent")
            holder.grid(row=0, column=0, sticky="nsew")
            holder.grid_remove()
            self._sections[sid] = {"item": item, "frame": holder,
                                   "builder": builder, "label": label,
                                   "built": False}
            self._panels[sid] = holder
            self._order.append(sid)
            return holder

        def _make_builder(self, tid):
            def build(parent):
                desc = TOOL_DESCRIPTIONS.get(tid, "")
                if desc:
                    ttk.Label(parent, text=desc, style="Sub.TLabel",
                              wraplength=306, justify="left").pack(
                        anchor="w", pady=(0, 10))
                getattr(self, "_panel_" + tid)(parent)
            return build

        def show(self, sid):
            """Switch tool panels (the canvas persists) and update the header."""
            try:
                self.canvas.disarm()
                self.canvas.clear_preview()
            except Exception:
                pass
            super().show(sid)
            self._current = self._sections.get(sid, {}).get("frame")
            self._clear_result()

        # Crawler-friendly navigation aliases.
        def _show_section(self, sid):
            self.show(sid)

        def _select_tool(self, tool_id):
            self.show(tool_id)

        # ---- menu ------------------------------------------------------
        def _build_menu(self):
            bar = tk.Menu(self)
            filem = tk.Menu(bar, tearoff=0)
            filem.add_command(label="Open…", accelerator="Ctrl+O",
                              command=self.open_image)
            self._recent_menu = tk.Menu(filem, tearoff=0)
            filem.add_cascade(label="Open Recent", menu=self._recent_menu)
            self._fill_recent_menu()
            filem.add_separator()
            filem.add_command(label="Save", accelerator="Ctrl+S", command=self.save_image)
            filem.add_command(label="Save As…", command=self.save_image_as)
            filem.add_command(label="Export…", command=lambda: self._select_tool("export"))
            filem.add_separator()
            filem.add_command(label="Exit", command=self.destroy)
            bar.add_cascade(label="File", menu=filem)

            editm = tk.Menu(bar, tearoff=0)
            editm.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
            editm.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
            bar.add_cascade(label="Edit", menu=editm)

            viewm = tk.Menu(bar, tearoff=0)
            viewm.add_command(label="Toggle dark mode", command=self.toggle_theme)
            viewm.add_separator()
            viewm.add_command(label="Zoom to fit", command=lambda: self.canvas.fit())
            viewm.add_command(label="Zoom in", command=lambda: self.canvas.zoom(1.25))
            viewm.add_command(label="Zoom out", command=lambda: self.canvas.zoom(0.8))
            bar.add_cascade(label="View", menu=viewm)

            helpm = tk.Menu(bar, tearoff=0)
            helpm.add_command(label="About", command=self._about)
            helpm.add_command(label="Project page (quickopen.ai)",
                              command=lambda: open_with_default_app(PROJECT_URL))
            bar.add_cascade(label="Help", menu=helpm)
            self.configure(menu=bar)

        def _bind_keys(self):
            self.bind_all("<Control-o>", lambda e: self.open_image())
            self.bind_all("<Control-s>", lambda e: self.save_image())
            self.bind_all("<Control-z>", lambda e: self.undo())
            self.bind_all("<Control-y>", lambda e: self.redo())

        def _fill_recent_menu(self):
            self._recent_menu.delete(0, "end")
            recent = guiconfig.get_recent()
            if not recent:
                self._recent_menu.add_command(label="(none)", state="disabled")
                return
            for path in recent:
                exists = os.path.exists(path)
                label = path if exists else path + "   (missing)"
                self._recent_menu.add_command(
                    label=label, state="normal" if exists else "disabled",
                    command=(lambda pp=path: self._load_path(pp)))
            self._recent_menu.add_separator()
            self._recent_menu.add_command(label="Clear list", command=self._clear_recent)

        def _clear_recent(self):
            guiconfig.clear_recent()
            self._fill_recent_menu()

        # ---- background op runner -------------------------------------
        def _bg(self, work, on_ok, button=None, busy="Working…", require_image=True):
            if self._busy:
                self._show_error("Please wait — an operation is already running.")
                return
            if require_image and self.image is None:
                self._show_error("Open an image first.")
                return
            self._busy = True
            if button is not None:
                try:
                    button.state(["disabled"])
                except Exception:
                    pass
            self._set_status(busy, kind="working")

            def run():
                try:
                    res, err = work(), None
                except ImgToolkitError as ex:
                    res, err = None, str(ex)
                except Exception as ex:
                    res, err = None, f"Unexpected error: {ex}"
                self.after(0, lambda: finish(res, err))

            def finish(res, err):
                self._busy = False
                if button is not None:
                    try:
                        button.state(["!disabled"])
                    except Exception:
                        pass
                if err is not None:
                    self._set_status("error", kind="err")
                    self._show_error(err)
                    return
                self._set_status("done", kind="ok")
                try:
                    on_ok(res)
                except Exception as ex:
                    self._show_error(f"Post-processing error: {ex}")

            threading.Thread(target=run, daemon=True).start()

        # ---- image lifecycle ------------------------------------------
        def open_image(self):
            p = filedialog.askopenfilename(title="Open image", filetypes=IMAGE_TYPES)
            if p:
                self._load_path(p)

        def _load_path(self, path):
            self._bg(lambda: io_util.load(path),
                     lambda img: self._set_new_image(img, path, fresh=True),
                     busy="Loading…", require_image=False)

        def _set_new_image(self, img, path=None, fresh=False):
            self.image = img
            if path:
                self.image_path = path
                guiconfig.add_recent(path)
                self._fill_recent_menu()
            if fresh:
                self.history.clear()
            self.history.push(img)
            self._proxy = None
            self.canvas.set_image(img)
            self._refresh_after_image()
            if path:
                self.report_success(f"Loaded {os.path.basename(path)}  "
                                    f"({img.shape[1]}×{img.shape[0]})")

        def commit(self, img, message):
            """Set a new working image and record it in undo history."""
            self.image = img
            self.history.push(img)
            self._proxy = None
            self.canvas.set_image(img)
            self._refresh_after_image()
            self.report_success(message)

        def _refresh_after_image(self):
            self._update_zoom_label()
            self._update_hist_label()
            if self.image is not None:
                h, w = self.image.shape[:2]
                ch = 1 if self.image.ndim == 2 else self.image.shape[2]
                self.size_lbl.configure(text=f"{w}×{h} · {ch}ch")

        def _update_zoom_label(self):
            self.zoom_lbl.configure(text=f"{int(self.canvas.scale * 100)}%"
                                    if self.canvas.has_image() else "—")

        def _update_hist_label(self):
            depth = len(self.history)
            self.hist_lbl.configure(
                text=f"history: {depth}/{self.history.max_depth}"
                     + ("  ⚠ large" if self.image is not None
                        and self.image.nbytes * depth > 400_000_000 else ""))

        def undo(self):
            if not self.history.can_undo():
                self._set_status("nothing to undo", kind="idle")
                return
            self.image = self.history.undo()
            self._proxy = None
            self.canvas.set_image(self.image)
            self._refresh_after_image()
            self._set_status("undo", kind="ok")

        def redo(self):
            if not self.history.can_redo():
                self._set_status("nothing to redo", kind="idle")
                return
            self.image = self.history.redo()
            self._proxy = None
            self.canvas.set_image(self.image)
            self._refresh_after_image()
            self._set_status("redo", kind="ok")

        def save_image(self):
            if self.image is None:
                self._show_error("Open an image first.")
                return
            if not self.image_path:
                return self.save_image_as()
            self._bg(lambda: io_util.save(self.image, self.image_path),
                     lambda pth: self.report_success(f"Saved → {pth}", [pth]))

        def save_image_as(self):
            if self.image is None:
                self._show_error("Open an image first.")
                return
            dest = filedialog.asksaveasfilename(
                title="Save image as", defaultextension=".png", filetypes=SAVE_TYPES)
            if not dest:
                return
            q = None
            if dest.lower().endswith((".jpg", ".jpeg", ".webp")):
                q = self._ask_quality()
            self._bg(lambda: io_util.save(self.image, dest, quality=q),
                     lambda pth: self._after_save_as(pth))

        def _after_save_as(self, pth):
            self.image_path = pth
            self.report_success(f"Saved → {pth}", [pth])

        def _ask_quality(self):
            win = tk.Toplevel(self)
            win.title("Quality")
            win.configure(bg=self._pal()["bg"])
            win.transient(self)
            var = tk.IntVar(value=90)
            ttk.Label(win, text="JPEG/WebP quality (1–100):",
                      style="TLabel").pack(padx=16, pady=(14, 6))
            ttk.Scale(win, from_=1, to=100, variable=var,
                      orient="horizontal", length=220).pack(padx=16)
            out = {"v": 90}
            def ok():
                out["v"] = int(var.get())
                win.destroy()
            ttk.Button(win, text="OK", command=ok).pack(pady=12)
            win.grab_set()
            self.wait_window(win)
            return out["v"]

        # ---- live-preview proxy ---------------------------------------
        def proxy(self):
            """Return a downscaled copy of the working image for fast preview."""
            if self.image is None:
                return None
            if self._proxy is not None and self._proxy_for == id(self.image):
                return self._proxy
            h, w = self.image.shape[:2]
            longest = max(h, w)
            if longest > MAX_PREVIEW:
                s = MAX_PREVIEW / longest
                self._proxy = transform.resize(
                    self.image, width=int(w * s), height=int(h * s),
                    keep_aspect=False)
            else:
                self._proxy = self.image
            self._proxy_for = id(self.image)
            return self._proxy

        def schedule_preview(self, compute):
            """Debounced live preview of ``compute`` applied to the proxy."""
            if self._preview_job:
                try:
                    self.after_cancel(self._preview_job)
                except Exception:
                    pass
            self._preview_job = self.after(110, lambda: self._do_preview(compute))

        def _do_preview(self, compute):
            self._preview_job = None
            base = self.proxy()
            if base is None:
                return
            try:
                out = compute(base)
            except Exception:
                return
            self.canvas.set_preview(out)

        def apply_op(self, compute, message, button=None):
            """Run ``compute`` on the full image off-thread, commit on success."""
            if self.image is None:
                self._show_error("Open an image first.")
                return
            img = self.image
            self._bg(lambda: compute(img),
                     lambda res: (self.canvas.clear_preview(),
                                  self.commit(res, message)), button=button)

        # ---- result / status bar (routed to the Aura inline status bar) ----
        def _set_status(self, text, kind="idle"):
            # Aura StatusBar understands kinds idle/working/ok/err directly.
            self.statusbar.set_status(text, kind)

        def _clear_result(self):
            if self.image is None:
                self.statusbar.set_status("Open an image to begin  (File ▸ Open)")
            else:
                self.statusbar.set_status("Ready")

        def _show_error(self, message):
            self.statusbar.set_error(message)

        def report_success(self, message, outputs=None):
            for o in (outputs or []):
                if o:
                    guiconfig.add_recent(o)
            if outputs:
                self._fill_recent_menu()
            self.statusbar.set_success(message)

        # ---- About -----------------------------------------------------
        def _about(self):
            win = tk.Toplevel(self)
            win.title("About Image Toolkit")
            win.configure(bg=self._pal()["bg"])
            win.resizable(False, False)
            frm = ttk.Frame(win, style="TFrame", padding=18)
            frm.pack(fill="both", expand=True)
            ttk.Label(frm, text="Image Toolkit", style="Header.TLabel").pack(anchor="w")
            ttk.Label(frm, text=f"Version {APP_VERSION}",
                      style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
            ttk.Label(frm, style="TLabel", justify="left", wraplength=400,
                      text="A fast, fully-offline image editor — crop, tone, "
                           "filters, retouch, annotate, layers and batch.\n\n"
                           "100% AI-built, open source, published on QuickOpen.\n"
                           "Nothing is ever uploaded anywhere.").pack(anchor="w")
            ttk.Label(frm, style="Sub.TLabel", justify="left", wraplength=400,
                      text="Licensed under Apache-2.0. Built on permissive "
                           "libraries: Pillow, numpy, OpenCV, scikit-image, "
                           "rawpy, piexif. AI/ML model weights are intentionally "
                           "NOT bundled so the app stays permissively licensed — "
                           "every 'smart' operation is classical computer "
                           "vision.").pack(anchor="w", pady=(8, 4))
            link = ttk.Label(frm, text="Project page: quickopen.ai",
                             style="Sub.TLabel", cursor="hand2")
            link.pack(anchor="w", pady=(4, 10))
            link.bind("<Button-1>", lambda e: open_with_default_app(PROJECT_URL))
            ttk.Button(frm, text="Close", command=win.destroy).pack(anchor="e")
            win.transient(self)
            win.grab_set()

        # ---- small panel helpers --------------------------------------
        def _apply_btn(self, parent, text="Apply"):
            # Aura primary button (ttk-compatible .state([...]) shim keeps the
            # _bg(..., button=btn) disable/enable dance working).
            b = aura.AuraButton(parent, text, kind="primary")
            b.pack(fill="x", pady=(12, 4))
            return b

        def _need(self):
            if self.image is None:
                self._show_error("Open an image first.")
                return False
            return True

        def _color_button(self, parent, label, default=(255, 0, 0)):
            state = {"rgb": default}
            row = ttk.Frame(parent, style="TFrame")
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=14, anchor="w").pack(side="left")
            sw = tk.Label(row, width=4, bg="#%02x%02x%02x" % default,
                          relief="ridge")
            sw.pack(side="left")

            def pick():
                rgb, _hexc = colorchooser.askcolor(color="#%02x%02x%02x" % state["rgb"])
                if rgb:
                    state["rgb"] = tuple(int(v) for v in rgb)
                    sw.configure(bg="#%02x%02x%02x" % state["rgb"])
            ttk.Button(row, text="Pick…", command=pick).pack(side="left", padx=6)
            return state

        # =================================================================
        # PANELS — each wires widgets to specific imgtoolkit core calls.
        # =================================================================

        # ---------- Transform ----------
        def _panel_crop(self, parent):
            info = ttk.Label(parent, style="Sub.TLabel", wraplength=300,
                             text="Click ‘Select area’, then drag a rectangle on "
                                  "the image.")
            info.pack(anchor="w", pady=2)
            state = {"box": None}
            box_lbl = ttk.Label(parent, text="No selection.", style="Muted.TLabel")

            def on_box(box):
                state["box"] = box
                box_lbl.configure(text=f"box = {box}")

            ttk.Button(parent, text="Select area",
                       command=lambda: self.canvas.arm_rect(on_box)).pack(
                fill="x", pady=4)
            box_lbl.pack(anchor="w", pady=2)
            btn = self._apply_btn(parent, "Crop")

            def go():
                if not self._need():
                    return
                if not state["box"]:
                    self._show_error("Drag a crop rectangle first.")
                    return
                self.apply_op(lambda im: transform.crop(im, state["box"]),
                              "Cropped", btn)
            btn.configure(command=go)

        def _panel_rotate(self, parent):
            row = ttk.Frame(parent, style="TFrame")
            row.pack(fill="x", pady=4)
            ttk.Button(row, text="⟲ 90°",
                       command=lambda: self._do_rotate(90)).pack(side="left", expand=True, fill="x")
            ttk.Button(row, text="⟳ 90°",
                       command=lambda: self._do_rotate(-90)).pack(side="left", expand=True, fill="x", padx=4)
            ttk.Button(row, text="180°",
                       command=lambda: self._do_rotate(180)).pack(side="left", expand=True, fill="x")
            self._rot_slider = SliderRow(parent, "Angle°", -180, 180, 0,
                                         fmt="{:.0f}")
            self._rot_slider.pack(fill="x", pady=(10, 2))
            self._rot_expand = tk.BooleanVar(value=True)
            ttk.Checkbutton(parent, text="Expand canvas to fit",
                            variable=self._rot_expand).pack(anchor="w")
            btn = self._apply_btn(parent, "Rotate by angle")
            btn.configure(command=lambda: self._do_rotate(self._rot_slider.value(),
                                                          self._rot_expand.get(), btn))

        def _do_rotate(self, deg, expand=True, button=None):
            self.apply_op(lambda im: transform.rotate(im, deg, expand=expand),
                          f"Rotated {deg:g}°", button)

        def _panel_straighten(self, parent):
            sld = SliderRow(parent, "Tilt°", -45, 45, 0, fmt="{:.1f}")
            sld.on_change = lambda v: self.schedule_preview(
                lambda im: transform.straighten(im, v))
            sld.pack(fill="x", pady=6)
            btn = self._apply_btn(parent, "Straighten")
            btn.configure(command=lambda: self.apply_op(
                lambda im: transform.straighten(im, sld.value()), "Straightened", btn))

        def _panel_flip(self, parent):
            ttk.Button(parent, text="Flip horizontal", style="Accent.TButton",
                       command=lambda: self.apply_op(
                           lambda im: transform.flip(im, "h"), "Flipped H")).pack(
                fill="x", pady=4)
            ttk.Button(parent, text="Flip vertical", style="Accent.TButton",
                       command=lambda: self.apply_op(
                           lambda im: transform.flip(im, "v"), "Flipped V")).pack(
                fill="x", pady=4)

        def _panel_resize(self, parent):
            w = LabeledEntry(parent, "Width (px)")
            w.pack(fill="x", pady=3)
            h = LabeledEntry(parent, "Height (px)")
            h.pack(fill="x", pady=3)
            keep = tk.BooleanVar(value=True)
            ttk.Checkbutton(parent, text="Keep aspect ratio",
                            variable=keep).pack(anchor="w", pady=2)
            rrow = ttk.Frame(parent, style="TFrame")
            rrow.pack(fill="x", pady=3)
            ttk.Label(rrow, text="Resample", width=14, anchor="w").pack(side="left")
            rs = tk.StringVar(value="auto")
            ttk.Combobox(rrow, textvariable=rs, values=RESAMPLE, state="readonly",
                         width=12).pack(side="left")
            btn = self._apply_btn(parent, "Resize")

            def go():
                if not self._need():
                    return
                wv, hv = w.get_int(), h.get_int()
                if not wv and not hv:
                    self._show_error("Enter a width and/or height.")
                    return
                self.apply_op(lambda im: transform.resize(
                    im, width=wv, height=hv, keep_aspect=keep.get(),
                    resample=rs.get()), "Resized", btn)
            btn.configure(command=go)

        def _panel_canvas(self, parent):
            w = LabeledEntry(parent, "Canvas width")
            w.pack(fill="x", pady=3)
            h = LabeledEntry(parent, "Canvas height")
            h.pack(fill="x", pady=3)
            arow = ttk.Frame(parent, style="TFrame")
            arow.pack(fill="x", pady=3)
            ttk.Label(arow, text="Anchor", width=14, anchor="w").pack(side="left")
            anch = tk.StringVar(value="center")
            ttk.Combobox(arow, textvariable=anch, values=ANCHORS, state="readonly",
                         width=12).pack(side="left")
            btn = self._apply_btn(parent, "Set canvas size")

            def go():
                if not self._need():
                    return
                wv, hv = w.get_int(), h.get_int()
                if not wv or not hv:
                    self._show_error("Enter both width and height.")
                    return
                self.apply_op(lambda im: transform.canvas_resize(
                    im, wv, hv, anchor=anch.get()), "Canvas resized", btn)
            btn.configure(command=go)

        def _panel_perspective(self, parent):
            ttk.Label(parent, style="Sub.TLabel", wraplength=300,
                      text="Click the 4 corners in order: top-left, top-right, "
                           "bottom-right, bottom-left.").pack(anchor="w", pady=2)
            state = {"quad": None}
            lbl = ttk.Label(parent, text="No corners placed.", style="Muted.TLabel")

            def on_quad(pts):
                state["quad"] = pts
                lbl.configure(text=f"{len(pts)} corners placed.")

            ttk.Button(parent, text="Place 4 corners",
                       command=lambda: self.canvas.arm_quad(4, on_quad)).pack(
                fill="x", pady=4)
            lbl.pack(anchor="w", pady=2)
            btn = self._apply_btn(parent, "Correct perspective")

            def go():
                if not self._need():
                    return
                if not state["quad"] or len(state["quad"]) != 4:
                    self._show_error("Place all 4 corners first.")
                    return
                self.apply_op(lambda im: transform.perspective_correct(
                    im, state["quad"]), "Perspective corrected", btn)
            btn.configure(command=go)

        # ---------- Color & Tone ----------
        def _light_compute(self, br, co, ex):
            def f(im):
                out = im
                if abs(br - 1) > 1e-3:
                    out = color.brightness(out, br)
                if abs(co - 1) > 1e-3:
                    out = color.contrast(out, co)
                if abs(ex) > 1e-3:
                    out = color.exposure(out, ex)
                return out
            return f

        def _panel_light(self, parent):
            br = SliderRow(parent, "Brightness", 0.2, 2.0, 1.0)
            co = SliderRow(parent, "Contrast", 0.2, 2.0, 1.0)
            ex = SliderRow(parent, "Exposure (EV)", -3, 3, 0, fmt="{:.2f}")
            for s in (br, co, ex):
                s.pack(fill="x", pady=4)
                s.on_change = lambda v: self.schedule_preview(
                    self._light_compute(br.value(), co.value(), ex.value()))
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(
                self._light_compute(br.value(), co.value(), ex.value()),
                "Light adjusted", btn))

        def _panel_tonemask(self, parent):
            hi = SliderRow(parent, "Highlights", -1, 1, 0, fmt="{:.2f}")
            sh = SliderRow(parent, "Shadows", -1, 1, 0, fmt="{:.2f}")

            def compute():
                return lambda im: color.highlights_shadows(
                    im, highlights=hi.value(), shadows=sh.value())
            for s in (hi, sh):
                s.pack(fill="x", pady=4)
                s.on_change = lambda v: self.schedule_preview(compute())
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(
                compute(), "Highlights/shadows", btn))

        def _panel_saturation(self, parent):
            sat = SliderRow(parent, "Saturation", 0, 2, 1.0)
            vib = SliderRow(parent, "Vibrance", -1, 1, 0, fmt="{:.2f}")
            hue = SliderRow(parent, "Hue°", -180, 180, 0, fmt="{:.0f}")

            def compute():
                def f(im):
                    out = im
                    if abs(sat.value() - 1) > 1e-3:
                        out = color.saturation(out, sat.value())
                    if abs(vib.value()) > 1e-3:
                        out = color.vibrance(out, vib.value())
                    if abs(hue.value()) > 1e-3:
                        out = color.hue_shift(out, hue.value())
                    return out
                return f
            for s in (sat, vib, hue):
                s.pack(fill="x", pady=4)
                s.on_change = lambda v: self.schedule_preview(compute())
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(compute(), "Colour adjusted", btn))

        def _panel_whitebalance(self, parent):
            ttk.Button(parent, text="Auto white balance", style="Accent.TButton",
                       command=lambda: self.apply_op(
                           lambda im: color.white_balance(im, auto=True),
                           "Auto white balance")).pack(fill="x", pady=(2, 10))
            temp = SliderRow(parent, "Temperature", -1, 1, 0, fmt="{:.2f}")
            tint = SliderRow(parent, "Tint", -1, 1, 0, fmt="{:.2f}")

            def compute():
                return lambda im: color.white_balance(
                    im, temp=temp.value(), tint=tint.value())
            for s in (temp, tint):
                s.pack(fill="x", pady=4)
                s.on_change = lambda v: self.schedule_preview(compute())
            btn = self._apply_btn(parent, "Apply temp/tint")
            btn.configure(command=lambda: self.apply_op(compute(), "White balance", btn))

        def _panel_levels(self, parent):
            ib = SliderRow(parent, "Input black", 0, 254, 0, fmt="{:.0f}")
            iw = SliderRow(parent, "Input white", 1, 255, 255, fmt="{:.0f}")
            gm = SliderRow(parent, "Gamma", 0.1, 3.0, 1.0)
            ob = SliderRow(parent, "Output black", 0, 255, 0, fmt="{:.0f}")
            ow = SliderRow(parent, "Output white", 0, 255, 255, fmt="{:.0f}")

            def compute():
                return lambda im: color.levels(
                    im, in_black=ib.value(), in_white=max(ib.value() + 1, iw.value()),
                    gamma=gm.value(), out_black=ob.value(), out_white=ow.value())
            for s in (ib, iw, gm, ob, ow):
                s.pack(fill="x", pady=3)
                s.on_change = lambda v: self.schedule_preview(compute())
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(compute(), "Levels", btn))

        def _panel_curves(self, parent):
            crow = ttk.Frame(parent, style="TFrame")
            crow.pack(fill="x")
            ttk.Label(crow, text="Channel", width=10, anchor="w").pack(side="left")
            chan = tk.StringVar(value="rgb")
            ttk.Combobox(crow, textvariable=chan,
                         values=["rgb", "r", "g", "b", "luma"], state="readonly",
                         width=8).pack(side="left")
            editor = CurveEditor(parent, self)
            editor.pack(pady=8)

            def compute():
                return lambda im: color.curves(im, chan.get(), editor.get_points())
            editor.on_change = lambda: self.schedule_preview(compute())
            chan.trace_add("write", lambda *_: self.schedule_preview(compute()))
            ttk.Button(parent, text="Reset curve", command=editor.reset).pack(
                fill="x", pady=2)
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(compute(), "Curves", btn))

        def _panel_colorbalance(self, parent):
            groups = {}
            for name in ("shadows", "midtones", "highlights"):
                lf = ttk.Labelframe(parent, text=name.title(), padding=6)
                lf.pack(fill="x", pady=4)
                r = SliderRow(lf, "R", -100, 100, 0, fmt="{:.0f}")
                g = SliderRow(lf, "G", -100, 100, 0, fmt="{:.0f}")
                b = SliderRow(lf, "B", -100, 100, 0, fmt="{:.0f}")
                for s in (r, g, b):
                    s.pack(fill="x", pady=1)
                    s.on_change = lambda v: self.schedule_preview(compute())
                groups[name] = (r, g, b)

            def trip(name):
                r, g, b = groups[name]
                return (r.value(), g.value(), b.value())

            def compute():
                return lambda im: color.color_balance(
                    im, shadows=trip("shadows"), midtones=trip("midtones"),
                    highlights=trip("highlights"))
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(compute(), "Colour balance", btn))

        def _panel_quickcolor(self, parent):
            ttk.Button(parent, text="Auto-enhance", style="Accent.TButton",
                       command=lambda: self.apply_op(color.auto_enhance,
                                                     "Auto-enhanced")).pack(fill="x", pady=4)
            ttk.Button(parent, text="Grayscale",
                       command=lambda: self.apply_op(
                           lambda im: color.grayscale(im, keep_channels=True),
                           "Grayscale")).pack(fill="x", pady=4)
            ttk.Button(parent, text="Invert",
                       command=lambda: self.apply_op(color.invert, "Inverted")).pack(
                fill="x", pady=4)
            sep = SliderRow(parent, "Sepia intensity", 0, 1, 1.0)
            sep.pack(fill="x", pady=(10, 2))
            ttk.Button(parent, text="Sepia", style="Accent.TButton",
                       command=lambda: self.apply_op(
                           lambda im: color.sepia(im, sep.value()), "Sepia")).pack(
                fill="x", pady=4)

        # ---------- Filters & Effects ----------
        def _panel_blur(self, parent):
            trow = ttk.Frame(parent, style="TFrame")
            trow.pack(fill="x")
            ttk.Label(trow, text="Type", width=10, anchor="w").pack(side="left")
            kind = tk.StringVar(value="gaussian")
            ttk.Combobox(trow, textvariable=kind,
                         values=["gaussian", "motion", "lens"], state="readonly",
                         width=12).pack(side="left")
            radius = SliderRow(parent, "Radius", 1, 40, 5, fmt="{:.0f}")
            angle = SliderRow(parent, "Angle° (motion)", 0, 180, 0, fmt="{:.0f}")
            dist = SliderRow(parent, "Distance (motion)", 1, 60, 15, fmt="{:.0f}")
            for s in (radius, angle, dist):
                s.pack(fill="x", pady=3)

            def compute():
                k = kind.get()
                if k == "gaussian":
                    return lambda im: filters.gaussian_blur(im, radius=radius.value())
                if k == "motion":
                    return lambda im: filters.motion_blur(
                        im, angle=angle.value(), distance=int(dist.value()))
                return lambda im: filters.lens_blur(im, radius=int(radius.value()))
            for s in (radius, angle, dist):
                s.on_change = lambda v: self.schedule_preview(compute())
            kind.trace_add("write", lambda *_: self.schedule_preview(compute()))
            btn = self._apply_btn(parent, "Apply blur")
            btn.configure(command=lambda: self.apply_op(compute(), "Blur", btn))

        def _panel_sharpenf(self, parent):
            amt = SliderRow(parent, "Amount", 0, 3, 1.0)
            rad = SliderRow(parent, "Radius", 0.5, 8, 2.0)
            thr = SliderRow(parent, "Threshold", 0, 50, 0, fmt="{:.0f}")

            def compute():
                return lambda im: filters.sharpen(
                    im, amount=amt.value(), radius=rad.value(),
                    threshold=int(thr.value()))
            for s in (amt, rad, thr):
                s.pack(fill="x", pady=3)
                s.on_change = lambda v: self.schedule_preview(compute())
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(compute(), "Sharpened", btn))

        def _panel_vignette(self, parent):
            st = SliderRow(parent, "Strength", 0, 1, 0.6)
            rd = SliderRow(parent, "Radius", 0.3, 2.0, 1.0)

            def compute():
                return lambda im: filters.vignette(im, strength=st.value(),
                                                   radius=rd.value())
            for s in (st, rd):
                s.pack(fill="x", pady=4)
                s.on_change = lambda v: self.schedule_preview(compute())
            btn = self._apply_btn(parent, "Apply")
            btn.configure(command=lambda: self.apply_op(compute(), "Vignette", btn))

        def _panel_effects(self, parent):
            erow = ttk.Frame(parent, style="TFrame")
            erow.pack(fill="x")
            ttk.Label(erow, text="Effect", width=10, anchor="w").pack(side="left")
            kind = tk.StringVar(value="hdr")
            ttk.Combobox(erow, textvariable=kind,
                         values=["hdr", "vintage", "pencil", "stylize", "oil",
                                 "cartoon"], state="readonly", width=12).pack(side="left")
            strength = SliderRow(parent, "Strength / fade", 0, 1, 0.5)
            strength.pack(fill="x", pady=4)
            colorv = tk.BooleanVar(value=False)
            ttk.Checkbutton(parent, text="Colour pencil sketch",
                            variable=colorv).pack(anchor="w")

            def compute():
                k = kind.get()
                if k == "hdr":
                    return lambda im: filters.hdr_effect(im, strength=strength.value())
                if k == "vintage":
                    return lambda im: filters.vintage(im, fade=strength.value())
                if k == "pencil":
                    return lambda im: filters.pencil_sketch(im, color=colorv.get())
                if k == "stylize":
                    return filters.stylize
                if k == "oil":
                    return lambda im: filters.oil_paint(im)
                return filters.cartoon

            def preview():
                self._bg(lambda: compute()(self.proxy()),
                         lambda res: self.canvas.set_preview(res),
                         busy="Rendering preview…")
            ttk.Button(parent, text="Preview", command=preview).pack(fill="x", pady=(10, 2))
            btn = self._apply_btn(parent, "Apply effect")
            btn.configure(command=lambda: self.apply_op(compute(), f"Effect: {kind.get()}", btn))

        def _panel_lut(self, parent):
            path = LabeledEntry(parent, ".cube file", width=18)
            path.pack(fill="x", pady=4)
            ttk.Button(parent, text="Browse…",
                       command=lambda: path.var.set(
                           filedialog.askopenfilename(filetypes=CUBE_TYPES) or
                           path.var.get())).pack(anchor="w")
            btn = self._apply_btn(parent, "Apply LUT")

            def go():
                if not self._need():
                    return
                if not path.get():
                    self._show_error("Choose a .cube LUT file.")
                    return
                self.apply_op(lambda im: filters.apply_lut(im, path.get()),
                              "LUT applied", btn)
            btn.configure(command=go)

        # ---------- Retouch ----------
        def _panel_denoise(self, parent):
            st = SliderRow(parent, "Strength", 1, 30, 10, fmt="{:.0f}")
            st.pack(fill="x", pady=6)
            btn = self._apply_btn(parent, "Denoise")
            btn.configure(command=lambda: self.apply_op(
                lambda im: retouch.denoise(im, strength=st.value()), "Denoised", btn))

        def _panel_skin(self, parent):
            st = SliderRow(parent, "Strength", 0, 1, 0.5)
            st.pack(fill="x", pady=6)
            btn = self._apply_btn(parent, "Smooth skin")
            btn.configure(command=lambda: self.apply_op(
                lambda im: retouch.skin_smooth(im, strength=st.value()),
                "Skin smoothed", btn))

        def _panel_redeye(self, parent):
            ttk.Label(parent, style="Sub.TLabel", wraplength=300,
                      text="Click ‘Select eye’, then drag over the red eye.").pack(
                anchor="w", pady=2)
            state = {"box": None}
            lbl = ttk.Label(parent, text="No selection.", style="Muted.TLabel")

            def on_box(box):
                state["box"] = box
                lbl.configure(text=f"region = {box}")
            ttk.Button(parent, text="Select eye",
                       command=lambda: self.canvas.arm_rect(on_box)).pack(fill="x", pady=4)
            lbl.pack(anchor="w", pady=2)
            btn = self._apply_btn(parent, "Remove red-eye")

            def go():
                if not self._need():
                    return
                if not state["box"]:
                    self._show_error("Drag over the eye first.")
                    return
                self.apply_op(lambda im: retouch.red_eye_removal(im, state["box"]),
                              "Red-eye removed", btn)
            btn.configure(command=go)

        def _panel_heal(self, parent):
            ttk.Label(parent, style="Sub.TLabel", wraplength=300,
                      text="Paint over the area to remove, then heal. Uses "
                           "classical inpainting (no AI).").pack(anchor="w", pady=2)
            brush = SliderRow(parent, "Brush size", 3, 120, 30, fmt="{:.0f}")
            brush.on_change = lambda v: setattr(self.canvas, "brush", int(v))
            brush.pack(fill="x", pady=4)
            mrow = ttk.Frame(parent, style="TFrame")
            mrow.pack(fill="x", pady=3)
            ttk.Label(mrow, text="Method", width=10, anchor="w").pack(side="left")
            method = tk.StringVar(value="telea")
            ttk.Combobox(mrow, textvariable=method, values=["telea", "ns"],
                         state="readonly", width=8).pack(side="left")
            rad = SliderRow(parent, "Inpaint radius", 1, 30, 10, fmt="{:.0f}")
            rad.pack(fill="x", pady=3)

            def start_paint():
                if not self._need():
                    return
                self.canvas.brush = int(brush.value())
                self.canvas.arm_mask()
            ttk.Button(parent, text="Paint mask", command=start_paint).pack(fill="x", pady=(8, 2))
            ttk.Button(parent, text="Clear mask",
                       command=self.canvas.clear_mask).pack(fill="x", pady=2)

            def spot():
                if not self._need():
                    return
                self.canvas.arm_point(lambda pt: self.apply_op(
                    lambda im: retouch.spot_removal(im, pt, radius=int(rad.value()),
                                                    method=method.get()),
                    "Spot healed"))
            ttk.Button(parent, text="Spot heal (click a point)",
                       command=spot).pack(fill="x", pady=(8, 2))
            btn = self._apply_btn(parent, "Remove masked area")

            def go():
                if not self._need():
                    return
                mask = self.canvas.mask_array()
                if mask is None or int(mask.max()) == 0:
                    self._show_error("Paint a mask first.")
                    return
                self.apply_op(lambda im: retouch.object_removal(
                    im, mask, method=method.get(), radius=int(rad.value())),
                    "Object removed", btn)
            btn.configure(command=go)

        # ---------- Annotate ----------
        def _panel_draw(self, parent):
            srow = ttk.Frame(parent, style="TFrame")
            srow.pack(fill="x", pady=3)
            ttk.Label(srow, text="Tool", width=8, anchor="w").pack(side="left")
            shape = tk.StringVar(value="brush")
            ttk.Combobox(srow, textvariable=shape,
                         values=["brush", "line", "arrow", "rectangle", "ellipse",
                                 "highlighter"], state="readonly", width=12).pack(side="left")
            width = SliderRow(parent, "Line width", 1, 40, 4, fmt="{:.0f}")
            width.pack(fill="x", pady=3)
            colst = self._color_button(parent, "Colour", (255, 40, 40))
            fillv = tk.BooleanVar(value=False)
            ttk.Checkbutton(parent, text="Fill (rectangle / ellipse)",
                            variable=fillv).pack(anchor="w", pady=2)

            def commit_stroke(fn, msg):
                self.apply_op(fn, msg)

            def start():
                if not self._need():
                    return
                k = shape.get()
                col = colst["rgb"]
                wv = int(width.value())
                if k in ("brush", "highlighter"):
                    def done(pts):
                        if len(pts) < 1:
                            return
                        if k == "brush":
                            commit_stroke(lambda im: annotate.brush_stroke(
                                im, pts, width=wv, color=col), "Brush stroke")
                        else:
                            commit_stroke(lambda im: annotate.highlighter(
                                im, pts, width=max(wv, 12), color=col), "Highlighter")
                    self.canvas.arm_free(done)
                elif k in ("line", "arrow"):
                    def done(pts):
                        s, e = pts[0], pts[1]
                        if k == "line":
                            commit_stroke(lambda im: annotate.draw_line(
                                im, s, e, color=col, width=wv), "Line")
                        else:
                            commit_stroke(lambda im: annotate.draw_arrow(
                                im, s, e, color=col, width=wv), "Arrow")
                    self.canvas.arm_two(done)
                else:  # rectangle / ellipse
                    def done(box):
                        fill = col if fillv.get() else None
                        if k == "rectangle":
                            commit_stroke(lambda im: annotate.draw_rect(
                                im, box, color=col, width=wv, fill=fill), "Rectangle")
                        else:
                            commit_stroke(lambda im: annotate.draw_ellipse(
                                im, box, color=col, width=wv, fill=fill), "Ellipse")
                    self.canvas.arm_rect(done)
            ttk.Button(parent, text="Draw on image", style="Accent.TButton",
                       command=start).pack(fill="x", pady=(10, 4))
            ttk.Label(parent, style="Muted.TLabel", wraplength=300,
                      text="Brush/highlighter: drag. Line/arrow: click 2 points. "
                           "Rectangle/ellipse: drag a box.").pack(anchor="w")

        def _panel_text(self, parent):
            txt = LabeledEntry(parent, "Text", width=18)
            txt.pack(fill="x", pady=3)
            size = SliderRow(parent, "Font size", 8, 160, 32, fmt="{:.0f}")
            size.pack(fill="x", pady=3)
            colst = self._color_button(parent, "Colour", (255, 255, 255))
            stroke = tk.BooleanVar(value=True)
            ttk.Checkbutton(parent, text="Black outline",
                            variable=stroke).pack(anchor="w", pady=2)

            def place():
                if not self._need():
                    return
                if not txt.get():
                    self._show_error("Enter some text.")
                    return
                def done(pt):
                    sw = 2 if stroke.get() else 0
                    self.apply_op(lambda im: annotate.add_text(
                        im, txt.get(), pt, font_size=int(size.value()),
                        color=colst["rgb"], stroke_width=sw), "Text added")
                self.canvas.arm_point(done)
            ttk.Button(parent, text="Place text (click canvas)", style="Accent.TButton",
                       command=place).pack(fill="x", pady=(10, 4))

        # ---------- Layers ----------
        def _panel_layers(self, parent):
            ttk.Label(parent, style="Sub.TLabel", wraplength=300,
                      text="Non-destructive compositing. The working image is the "
                           "base layer; add more and blend.").pack(anchor="w", pady=2)
            tree = ttk.Treeview(parent, columns=("info",), show="tree",
                                height=6, selectmode="browse")
            tree.pack(fill="x", pady=6)

            state = {"doc": None}

            def ensure_doc():
                if state["doc"] is None:
                    if self.image is None:
                        return None
                    doc = layers.Document()
                    doc.add_image(self.image, name="Base")
                    state["doc"] = doc
                return state["doc"]

            def refresh():
                tree.delete(*tree.get_children())
                doc = state["doc"]
                if not doc:
                    return
                for i in range(len(doc) - 1, -1, -1):
                    ly = doc.layers[i]
                    vis = "◉" if ly.visible else "○"
                    name = ly.name or f"Layer {i}"
                    tree.insert("", "end", iid=str(i),
                                text=f"{vis} {name}  [{ly.blend_mode} {int(ly.opacity*100)}%]")

            def sel_index():
                s = tree.selection()
                return int(s[0]) if s else None

            def add_layer():
                doc = ensure_doc()
                if doc is None:
                    self._show_error("Open a base image first.")
                    return
                p = filedialog.askopenfilename(title="Add image layer",
                                               filetypes=IMAGE_TYPES)
                if not p:
                    return
                def work():
                    im = io_util.load(p)
                    if (im.shape[1], im.shape[0]) != (doc.width, doc.height):
                        im = transform.resize(im, width=doc.width, height=doc.height,
                                              keep_aspect=False)
                    doc.add_image(im, name=os.path.basename(p))
                    return True
                self._bg(work, lambda _r: (refresh(), render_preview()),
                         busy="Loading layer…")

            def move(delta):
                doc = state["doc"]
                i = sel_index()
                if not doc or i is None:
                    return
                j = i + delta
                if 0 <= j < len(doc):
                    doc.move_layer(i, j)
                    refresh()
                    tree.selection_set(str(j))
                    render_preview()

            def remove():
                doc = state["doc"]
                i = sel_index()
                if doc and i is not None and len(doc) > 1:
                    doc.remove_layer(i)
                    refresh()
                    render_preview()

            def toggle_vis():
                doc = state["doc"]
                i = sel_index()
                if doc and i is not None:
                    doc.layers[i].visible = not doc.layers[i].visible
                    refresh()
                    render_preview()

            def apply_props(_=None):
                doc = state["doc"]
                i = sel_index()
                if doc and i is not None:
                    doc.layers[i].opacity = float(opacity.value())
                    doc.layers[i].blend_mode = blend.get()
                    refresh()
                    render_preview()

            def render_preview():
                doc = state["doc"]
                if not doc:
                    return
                try:
                    out = doc.render(keep_alpha=False)
                except ImgToolkitError as ex:
                    self._show_error(str(ex))
                    return
                self.canvas.set_preview(out)

            def on_select(_e):
                doc = state["doc"]
                i = sel_index()
                if doc and i is not None:
                    ly = doc.layers[i]
                    opacity.set(ly.opacity)
                    blend.set(ly.blend_mode)
            tree.bind("<<TreeviewSelect>>", on_select)

            brow = ttk.Frame(parent, style="TFrame")
            brow.pack(fill="x")
            ttk.Button(brow, text="Add…", command=add_layer).pack(side="left")
            ttk.Button(brow, text="Up", width=4, command=lambda: move(1)).pack(side="left", padx=2)
            ttk.Button(brow, text="Down", width=5, command=lambda: move(-1)).pack(side="left")
            ttk.Button(brow, text="👁", width=3, command=toggle_vis).pack(side="left", padx=2)
            ttk.Button(brow, text="✕", width=3, command=remove).pack(side="left")

            opacity = SliderRow(parent, "Opacity", 0, 1, 1.0)
            opacity.on_change = lambda v: apply_props()
            opacity.pack(fill="x", pady=(8, 2))
            crow = ttk.Frame(parent, style="TFrame")
            crow.pack(fill="x", pady=3)
            ttk.Label(crow, text="Blend", width=8, anchor="w").pack(side="left")
            blend = tk.StringVar(value="normal")
            ttk.Combobox(crow, textvariable=blend, state="readonly", width=14,
                         values=sorted(layers.BLEND_MODES)).pack(side="left")
            blend.trace_add("write", lambda *_: apply_props())

            ttk.Button(parent, text="Render preview", command=render_preview).pack(
                fill="x", pady=(10, 2))
            btn = self._apply_btn(parent, "Flatten → working image")

            def flatten():
                doc = state["doc"]
                if not doc:
                    self._show_error("Add at least one layer first.")
                    return
                self._bg(lambda: doc.render(keep_alpha=False),
                         lambda out: (self.canvas.clear_preview(),
                                      self.commit(out, "Flattened layers")), button=btn)
            btn.configure(command=flatten)
            ttk.Button(parent, text="Start / reset from working image",
                       command=lambda: (state.update(doc=None), ensure_doc(),
                                        refresh(), render_preview())).pack(fill="x", pady=2)
            ensure_doc()
            refresh()

        # ---------- Batch ----------
        def _panel_batch(self, parent):
            ttk.Label(parent, text="Input files:", style="TLabel").pack(anchor="w")
            flist = FileList(parent, self)
            flist.pack(fill="x", pady=4)
            outrow = ttk.Frame(parent, style="TFrame")
            outrow.pack(fill="x", pady=3)
            ttk.Label(outrow, text="Output dir", width=10, anchor="w").pack(side="left")
            outdir = tk.StringVar()
            ttk.Entry(outrow, textvariable=outdir).pack(side="left", fill="x", expand=True)
            ttk.Button(outrow, text="…",
                       command=lambda: outdir.set(
                           filedialog.askdirectory() or outdir.get())).pack(side="left")

            orow = ttk.Frame(parent, style="TFrame")
            orow.pack(fill="x", pady=6)
            ttk.Label(orow, text="Operation", width=10, anchor="w").pack(side="left")
            op = tk.StringVar(value="resize")
            ttk.Combobox(orow, textvariable=op, state="readonly", width=16,
                         values=["resize", "convert", "watermark", "strip-metadata"]).pack(side="left")

            params = ttk.Frame(parent, style="TFrame")
            params.pack(fill="x", pady=4)
            w = LabeledEntry(params, "Width", "1920")
            h = LabeledEntry(params, "Height", "")
            fmt = LabeledEntry(params, "Format", "webp")
            wm = LabeledEntry(params, "WM text", "© QuickOpen")

            def refresh_params(*_):
                for ch in params.winfo_children():
                    ch.pack_forget()
                o = op.get()
                if o == "resize":
                    w.pack(fill="x", pady=2)
                    h.pack(fill="x", pady=2)
                    fmt.pack(fill="x", pady=2)
                elif o == "convert":
                    fmt.pack(fill="x", pady=2)
                elif o == "watermark":
                    wm.pack(fill="x", pady=2)
            op.trace_add("write", refresh_params)
            refresh_params()

            btn = self._apply_btn(parent, "Run batch")
            summ = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=300)
            summ.pack(anchor="w", pady=4)

            def go():
                inputs = flist.items()
                d = outdir.get().strip()
                if not inputs or not d:
                    self._show_error("Add input files and choose an output folder.")
                    return
                o = op.get()
                if o == "resize":
                    work = lambda: batch.batch_resize(
                        inputs, d, width=w.get_int(), height=h.get_int(),
                        out_format=(fmt.get() or None))
                elif o == "convert":
                    if not fmt.get():
                        self._show_error("Enter an output format.")
                        return
                    work = lambda: batch.batch_convert(inputs, d, fmt.get())
                elif o == "watermark":
                    work = lambda: batch.batch_watermark(inputs, d, text=wm.get())
                else:
                    work = lambda: batch.batch_strip_metadata(inputs, d)
                summ.configure(text=f"Processing {len(inputs)} file(s)…")
                self._bg(work, lambda res: (
                    summ.configure(text=f"Wrote {len(res)} file(s)."),
                    self.report_success(f"Batch {o}: {len(res)} file(s) → {d}", [d])),
                    button=btn, require_image=False)
            btn.configure(command=go)

        # ---------- File / Export ----------
        def _panel_export(self, parent):
            ttk.Label(parent, text="Preset export:", style="TLabel").pack(anchor="w")
            prow = ttk.Frame(parent, style="TFrame")
            prow.pack(fill="x", pady=4)
            preset = tk.StringVar(value=export.list_presets()[0])
            ttk.Combobox(prow, textvariable=preset, state="readonly", width=18,
                         values=export.list_presets()).pack(side="left")
            pbtn = ttk.Button(parent, text="Export with preset…", style="Accent.TButton")
            pbtn.pack(fill="x", pady=4)

            def go_preset():
                if not self._need():
                    return
                dest = filedialog.asksaveasfilename(title="Export as",
                                                    filetypes=SAVE_TYPES)
                if not dest:
                    return
                self._bg(lambda: export.export_preset(self.image, dest, preset.get()),
                         lambda pth: self.report_success(
                             f"Exported ({preset.get()}) → {pth}", [pth]), button=pbtn)
            pbtn.configure(command=go_preset)

            ttk.Separator(parent).pack(fill="x", pady=10)
            ttk.Label(parent, text="Custom export:", style="TLabel").pack(anchor="w")
            fmt = LabeledEntry(parent, "Format", "jpg")
            fmt.pack(fill="x", pady=3)
            q = SliderRow(parent, "Quality", 1, 100, 90, fmt="{:.0f}")
            q.pack(fill="x", pady=3)
            mw = LabeledEntry(parent, "Max width", "")
            mw.pack(fill="x", pady=3)
            mh = LabeledEntry(parent, "Max height", "")
            mh.pack(fill="x", pady=3)
            strip = tk.BooleanVar(value=False)
            ttk.Checkbutton(parent, text="Strip metadata",
                            variable=strip).pack(anchor="w", pady=2)
            cbtn = self._apply_btn(parent, "Custom export…")

            def go_custom():
                if not self._need():
                    return
                dest = filedialog.asksaveasfilename(title="Export as",
                                                    filetypes=SAVE_TYPES)
                if not dest:
                    return
                resize = None
                if mw.get_int() or mh.get_int():
                    resize = (mw.get_int() or 100000, mh.get_int() or 100000)
                self._bg(lambda: export.export(
                    self.image, dest, fmt=(fmt.get() or None), quality=int(q.value()),
                    strip_metadata=strip.get(), resize=resize),
                    lambda pth: self.report_success(f"Exported → {pth}", [pth]),
                    button=cbtn)
            cbtn.configure(command=go_custom)

    return App


def main():
    """Entry point: build the root window and run.  Degrades on headless hosts.

    Importing this module does nothing; only this function creates a Tk root.
    With no display (e.g. a server) it prints a friendly note and returns 0
    instead of raising.
    """
    try:
        import tkinter as tk
    except Exception as exc:
        print(f"{APP_NAME}: a graphical environment with tkinter is required "
              f"to run the GUI ({exc}).")
        return 0

    try:
        App = build_app()
        app = App()
    except ImportError as exc:
        print(f"{APP_NAME}: the GUI needs the 'customtkinter' package "
              f"({exc}). Install it with:  pip install customtkinter")
        return 0
    except tk.TclError as exc:
        print(f"{APP_NAME}: no graphical display available — cannot start the "
              f"GUI here ({exc}). This app is intended for the Windows desktop.")
        return 0
    except Exception as exc:
        print(f"{APP_NAME}: could not start the GUI ({exc}).")
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
