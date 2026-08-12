# Image Toolkit

A fast, **offline**, **100% open-source** image editor and batch processor for
Windows. Everything runs on your own machine — nothing is uploaded anywhere.
Built entirely by AI with human testing and guidance, and published on
[QuickOpen](https://quickopen.ai/projects/image-toolkit).

> **100% AI-built and open source.** Apache-2.0.

## What it does

**Essential editing** — crop, rotate, straighten, flip, resize (aspect lock),
canvas size, perspective correction, auto-enhance, undo/redo.

**Color & tone** — brightness, contrast, exposure, highlights & shadows, white
balance (auto gray-world), saturation, vibrance, hue, curves, levels, color
balance, grayscale/invert/sepia.

**Retouching** — heal / spot removal / object removal (classical inpainting),
clone stamp, red-eye removal, skin smoothing, sharpening, and noise reduction.

**Filters & effects** — Gaussian / motion / lens blur, unsharp sharpen, vignette,
HDR effect, vintage/film looks, pencil sketch, stylize, oil, cartoon, and 3D
`.cube` **LUT** support.

**Selection, layers & non-destructive editing** — a full layer model with image
and adjustment layers, per-layer opacity, masks, and 9 blend modes (normal,
multiply, screen, overlay, darken, lighten, difference, add, soft-light),
composited with correct source-over math.

**Advanced** — content-aware (seam-carve) scaling, liquify/warp, **panorama
stitching**, **HDR merge**, and **focus stacking**.

**Annotation** — brush, shapes, lines, arrows, text, highlighter.

**Batch** — resize, convert, watermark, strip-metadata, and rename across many
files with deterministic output names.

**RAW support** — open camera RAW files (CR2/NEF/ARW/DNG/RAF/RW2 …) via LibRaw.

**Export** — JPEG / PNG / WebP / TIFF / BMP with quality/compression controls,
metadata removal, watermarking, and export presets.

A desktop **GUI editor** (dark mode, zoom, layers, undo/redo, recent files) and a
full **command-line interface** are both included.

## Not included (and why)

To stay **100% open source and permissively licensed**, the deep-learning "AI
photo" features are intentionally **not bundled** — they depend on pretrained
model weights that are almost always non-commercial or otherwise
non-permissive, which would compromise the license:

- AI **background removal** and ML **object removal / content-aware fill**
- AI **upscaling / super-resolution**
- **Face enhancement**, old-photo **colorization**, and **deblurring**

Their *classical* counterparts that **are** open source stay in: inpainting-based
spot/object removal, noise reduction, sharpening, seam-carve content-aware
scaling, HDR merge, and panorama stitching. (A future optional add-on could wire
up permissively-licensed models where they exist.)

## Install

Download **`ImageToolkit-Setup.exe`** from the
[QuickOpen page](https://quickopen.ai/projects/image-toolkit) or the
[GitHub release](https://github.com/quickpod/image-toolkit/releases/latest) and
double-click it. It installs per-user (no admin), adds Desktop and Start Menu
shortcuts, and can optionally trust the QuickOpen Root CA. The installer is
Authenticode-signed by the QuickOpen Code Signing CA — verify it at
[quickopen.ai/trust](https://quickopen.ai/trust).

## Run from source

```sh
pip install -r requirements.txt
python image_toolkit_app.py          # GUI editor
python -m imgtoolkit --help          # CLI
```

### CLI examples

```sh
python -m imgtoolkit resize in.jpg out.jpg --width 1600
python -m imgtoolkit convert in.png out.webp --quality 82
python -m imgtoolkit autoenhance in.jpg out.jpg
python -m imgtoolkit filter in.jpg out.jpg vignette
python -m imgtoolkit denoise in.jpg out.jpg
python -m imgtoolkit inpaint in.jpg out.jpg --mask mask.png
python -m imgtoolkit content-aware-scale in.jpg out.jpg --width 1200
python -m imgtoolkit hdr-merge a.jpg b.jpg c.jpg out.jpg
python -m imgtoolkit stitch left.jpg right.jpg pano.jpg
python -m imgtoolkit batch resize photos/ out/ --width 1024
```

See [`imgtoolkit/README-API.md`](imgtoolkit/README-API.md) for the full library
API, and run any subcommand with `--help` for its flags.

## Built with (all permissive / weak-copyleft — no AGPL, no proprietary)

[Pillow](https://pypi.org/project/Pillow/) (HPND) ·
[NumPy](https://pypi.org/project/numpy/) (BSD) ·
[OpenCV](https://pypi.org/project/opencv-python/) (Apache-2.0) ·
[scikit-image](https://pypi.org/project/scikit-image/) (BSD) ·
[rawpy](https://pypi.org/project/rawpy/) / LibRaw (LGPL/CDDL) ·
[piexif](https://pypi.org/project/piexif/) (MIT).

## License

Apache-2.0 — see [LICENSE](LICENSE). A 100% AI-built project published on
QuickOpen; the only human involvement is testing and guidance.
