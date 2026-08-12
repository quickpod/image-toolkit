# imgtoolkit — API Reference

`imgtoolkit` is a headless, cross-platform image-editing toolkit for Python.
Apache-2.0, built exclusively on permissive / weak-copyleft dependencies
(Pillow, numpy, OpenCV, scikit-image, rawpy, piexif). **No** deep-learning
model weights are used; every "smart" operation is classical computer vision.

A separate GUI editor is built on top of this package, so the API is designed
to be clean and importable.

## Conventions

- **Images are `numpy.ndarray`, dtype `uint8`.** Colour images are **RGB**
  (3-channel) or **RGBA** (4-channel) — the same channel order as Pillow, not
  OpenCV's BGR. Grayscale is a 2-D `(H, W)` array. Conversions to/from BGR
  happen internally only when calling OpenCV.
- Colour operations **preserve the alpha channel** untouched.
- Every function takes explicit inputs (ndarray or file path) and returns a
  **new** array (or writes a file). Nothing mutates its input in place.
- On any failure a function raises **`imgtoolkit.errors.ImgToolkitError`**
  (or a subclass). The CLI turns that into a clean message + non-zero exit.

```python
from imgtoolkit import io_util, color, filters, export
img = io_util.load("photo.jpg")           # -> RGB/RGBA uint8 ndarray
img = color.auto_enhance(img)
img = filters.sharpen(img, amount=1.2)
export.export_preset(img, "out", "web-jpeg")
```

Top-level convenience re-exports: `load`, `save`, `Document`, `ImageLayer`,
`AdjustmentLayer`, `Layer`, `blend`, `BLEND_MODES`, `History`,
`ImgToolkitError`, `UnsupportedFormatError`, `DependencyError`.

---

## `errors`

- `ImgToolkitError(Exception)` — base error for all operations.
- `UnsupportedFormatError(ImgToolkitError)` — unreadable/unwritable format.
- `DependencyError(ImgToolkitError)` — optional dependency missing (e.g. rawpy).

---

## `io_util` — loading & saving

- `load(path) -> ndarray` — Load any supported image as RGB/RGBA `uint8`.
  RAW files (`.cr2/.cr3/.nef/.arw/.dng/.raf/.rw2/.orf/.pef/.srw/...`) are
  demosaiced via **rawpy** when installed; everything else via Pillow (with an
  OpenCV fallback). Alpha preserved. Raises if the file is missing/undecodable.
- `save(img, path, quality=None, strip_metadata=False) -> str` — Save by
  extension (PNG/JPEG/WebP/TIFF/BMP/...). `quality` (1–100) applies to
  JPEG/WebP. Alpha-less targets (JPEG/BMP) composite RGBA onto white. Returns
  the path written. Writing RAW is rejected.
- `encode(img, fmt, quality=None) -> bytes` — Encode to an in-memory blob.
- `image_info(path) -> dict` — `{width, height, mode/channels, format, has_alpha}`
  without a full decode (for non-RAW).
- `is_raw_path(path) -> bool` — True for known RAW extensions.
- Constants: `RAW_EXTENSIONS`, `PILLOW_EXTENSIONS`, `RAWPY_AVAILABLE`.

---

## `transform` — geometry

- `crop(img, box) -> ndarray` — `box = (left, top, right, bottom)`, right/bottom
  exclusive.
- `rotate(img, deg, expand=True, fill=(0,0,0,0)) -> ndarray` — CCW rotation;
  `expand` grows the canvas to fit. Transparent/black fill.
- `straighten(img, angle) -> ndarray` — Rotate but keep the original frame size.
- `flip(img, mode='h') -> ndarray` — `'h'` or `'v'`.
- `resize(img, width=None, height=None, keep_aspect=True, resample='auto') -> ndarray`
  — Provide either/both dims. `resample`: `auto`/nearest/bilinear/bicubic/
  area/lanczos.
- `canvas_resize(img, width, height, anchor='center', fill=(0,0,0,0)) -> ndarray`
  — Place on a fixed canvas without scaling (pad or crop). `anchor` e.g.
  `'top-left'`, `'center'`, `'bottom-right'`.
- `perspective_correct(img, src_quad, out_size=None) -> ndarray` — Warp a
  4-point quad (TL, TR, BR, BL) to a rectangle via
  `cv2.getPerspectiveTransform` / `warpPerspective`.

---

## `color` — tone & colour

All return a new image; alpha preserved.

- `brightness(img, factor)` — 1.0 = unchanged.
- `contrast(img, factor)` — about mid-grey 128.
- `exposure(img, ev)` — exposure in stops (gain = 2**ev).
- `highlights_shadows(img, highlights=0.0, shadows=0.0)` — each in [-1,1],
  luminance-masked.
- `saturation(img, factor)` — 0 = grayscale.
- `vibrance(img, amount)` — boosts low-saturation pixels more (~[-1,1]).
- `hue_shift(img, degrees)` — rotate hue 0–360.
- `white_balance(img, temp=0.0, tint=0.0, auto=False)` — `auto=True` = gray-world;
  else manual temp (warm+/cool−) and tint (magenta+/green−), each [-1,1].
- `curves(img, channel, control_points)` — piecewise-linear tone curve.
  `channel`: `'rgb'|'r'|'g'|'b'|'luma'`; points `[(in,out), ...]` in 0–255.
- `levels(img, in_black=0, in_white=255, gamma=1.0, out_black=0, out_white=255)`
  — Photoshop-style levels.
- `color_balance(img, shadows=(0,0,0), midtones=(0,0,0), highlights=(0,0,0))`
  — per-tonal-range RGB offsets (~[-100,100]).
- `grayscale(img, keep_channels=True)` — Rec.601 luma; `keep_channels=False`
  returns 2-D.
- `invert(img)` — photographic negative.
- `sepia(img, intensity=1.0)`.
- `autocontrast(img, clip_percent=0.5)` — per-channel percentile stretch.
- `auto_enhance(img)` — autocontrast + gray-world WB + mild saturation.

---

## `filters` — blur, sharpen, effects, LUTs

- `gaussian_blur(img, radius=3.0)`.
- `motion_blur(img, angle=0.0, distance=15)` — directional streak.
- `lens_blur(img, radius=7)` — disc/bokeh approximation.
- `sharpen(img, amount=1.0, radius=2.0, threshold=0)` — unsharp mask.
  Alias: `unsharp_mask`.
- `vignette(img, strength=0.6, radius=1.0)`.
- `hdr_effect(img, strength=0.5)` — single-image local-contrast look via
  `cv2.detailEnhance` (not an exposure merge).
- `vintage(img, fade=0.2, grain=12.0, seed=0)` — film look; grain is seeded.
  Alias: `film`.
- `pencil_sketch(img, color=False)` — `cv2.pencilSketch`.
- `stylize(img)` — `cv2.stylization`.
- `oil_paint(img, size=7, dyn_ratio=1)` — `cv2.xphoto.oilPainting` when
  available, else an edge-preserving/posterize approximation.
- `cartoon(img)` — edge mask over a bilateral-smoothed image.
- `parse_cube_lut(path) -> (table, size, dmin, dmax)` — parse an Adobe `.cube`
  3-D LUT (raises on 1-D or malformed).
- `apply_lut(img, cube_path)` — apply a 3-D LUT with trilinear interpolation.

---

## `retouch` — healing, inpainting, denoise

The inpainting-based functions use **CLASSICAL** inpainting (`cv2.inpaint`,
Telea / Navier-Stokes) — not generative AI, no model weights.

- `heal(img, mask=None, point=None, radius=10, method='telea')` — supply a
  mask **or** a `point=(x,y)`+radius. `method`: `'telea'|'ns'`.
- `spot_removal(img, point, radius=10, method='telea')` — blemish at a point.
- `object_removal(img, mask, method='telea', radius=10)` — remove a masked
  region (classical inpainting).
- `clone_stamp(img, src, dst, radius=15, feather=0.4)` — programmatic clone of
  a circular patch (headless core; the interactive brush is GUI-side).
- `red_eye_removal(img, region)` — `region=(l,t,r,b)`; desaturates red pixels.
- `skin_smooth(img, strength=0.5)` — edge-preserving bilateral smoothing.
- `denoise(img, strength=10.0)` — `cv2.fastNlMeansDenoisingColored`.
- `reduce_noise(img, level='medium')` — `'low'|'medium'|'high'`.

---

## `effects_advanced` — multi-step effects

- `content_aware_scale(img, width) -> ndarray` — seam-carve the width down to
  `width` keeping height. Uses scikit-image's `seam_carve` when present, else a
  correct built-in DP seam remover (this environment uses the built-in). Only
  width reduction is supported.
- `liquify(img, center, radius, strength, mode='push', direction=(1,0))` —
  local warp via displacement remap. `mode`: `'push'|'bloat'|'pinch'`.
  Alias: `warp(img, center, radius, strength, direction)` (push).
- `panorama_stitch(images) -> ndarray` — `cv2.Stitcher` over overlapping frames.
- `hdr_merge(images, exposures=None) -> ndarray` — exposure-free HDR via
  `cv2.MergeMertens` (exposure fusion; `exposures` accepted but unused).
- `focus_stack(images, align=True) -> ndarray` — align (ECC) + per-pixel
  Laplacian sharpness selection for an all-in-focus result.

---

## `annotate` — drawing (Pillow ImageDraw on RGBA overlays)

All return an **RGBA** ndarray with the annotation composited over the input.
Colours are RGB or RGBA tuples.

- `draw_rect(img, box, color=(255,0,0), width=3, fill=None)`.
- `draw_ellipse(img, box, color=(255,0,0), width=3, fill=None)`.
- `draw_line(img, start, end, color=(255,0,0), width=3)`.
- `draw_arrow(img, start, end, color=(255,0,0), width=3, head_size=None)`.
- `add_text(img, text, xy, font_size=24, color=(255,255,255), font_path=None,
  anchor='la', stroke_width=0, stroke_color=(0,0,0))`.
- `brush_stroke(img, points, width=8, color=(0,0,0))`.
- `highlighter(img, points, width=16, color=(255,255,0), alpha=100)`.

---

## `watermark`

- `text_watermark(img, text, opacity=0.5, position='bottom-right', rotation=0.0,
  size=32, color=(255,255,255), margin=16, font_path=None) -> RGBA`.
- `image_watermark(img, overlay_path, opacity=0.5, position='bottom-right',
  scale=0.2, margin=16) -> RGBA`.

`position` is one of: top-left, top, top-right, left, center, right,
bottom-left, bottom, bottom-right.

---

## `metadata` — EXIF (piexif)

- `read_exif(path) -> dict` — flat `{tag_name: value}`; `{}` for formats that
  carry no readable EXIF (PNG/WebP/...).
- `strip_metadata(in_path, out_path) -> str` — re-encode with all EXIF removed.
- `set_exif(in_path, out_path, fields) -> str` — write EXIF by friendly name
  (JPEG/TIFF only). Known fields: Make, Model, Software, Artist, Copyright,
  ImageDescription, DateTime, DateTimeOriginal, UserComment.

---

## `export` — presets & export

- `export(img, path, fmt=None, quality=None, strip_metadata=False, resize=None) -> str`
  — `resize=(max_w, max_h)` fits inside keeping aspect; `fmt` overrides the
  extension.
- `export_preset(img, path, preset) -> str` — apply a named preset (forces its
  format/extension).
- `list_presets() -> list[str]`.
- `PRESETS: dict` — named presets: `web-jpeg`, `web-webp`, `web-thumb`,
  `print-tiff`, `print-jpeg`, `archive-png`, `social-square`. Each has
  `{fmt, quality, resize, strip_metadata}`.

---

## `batch` — pipeline runner

- `batch_apply(inputs, out_dir, ops, naming='{name}{ext}', out_format=None,
  quality=None) -> list[str]` — run `ops = [(op_name, kwargs), ...]` (keys of
  `batch.OPS`) over each input; deterministic output names. `naming`
  placeholders: `{index}` / `{i}`, `{name}` / `{stem}` (input stem), `{ext}`
  (with dot). Supports format specs, e.g. `'frame_{index:03d}{ext}'`.
- `batch_resize(inputs, out_dir, width=None, height=None, keep_aspect=True,
  out_format=None, quality=None, naming='{name}{ext}')`.
- `batch_convert(inputs, out_dir, out_format, quality=None, naming='{name}{ext}')`.
- `batch_watermark(inputs, out_dir, text=None, overlay_path=None,
  out_format=None, quality=None, naming='{name}{ext}', **wm_kwargs)`.
- `batch_strip_metadata(inputs, out_dir, naming='{name}{ext}')`.
- `batch_rename(inputs, out_dir, pattern='{name}_{index}{ext}', start=0)` —
  copy/rename, no pixel changes.
- `OPS: dict` — registry of array→array ops usable in a pipeline (the GUI can
  introspect it to build menus).

---

## `history` — undo/redo

`History(max_depth=25)` — bounded linear undo/redo of full numpy snapshots.

- `push(img)` — record a new current state (stores a copy; drops the redo tail).
- `undo() -> ndarray`, `redo() -> ndarray`, `current() -> ndarray`.
- `can_undo() -> bool`, `can_redo() -> bool`, `clear()`, `len(history)`.

**Memory note:** stores full snapshots, so peak memory ≈
`depth × H × W × channels` bytes. Simple and correct; for very large images a
GUI may prefer tile/patch diffs. `max_depth` caps the memory.

---

## `layers` — non-destructive compositing

The backbone of layers / non-destructive editing. Composites bottom-to-top
using the W3C blend + Porter-Duff *source-over* formula in float.

- `BLEND_MODES: dict` — `normal, multiply, screen, overlay, darken, lighten,
  difference, add, softlight`.
- `blend(backdrop, source, mode='normal') -> ndarray` — the blend math on
  arrays in [0,1] (per channel).
- `Layer(opacity=1.0, blend_mode='normal', mask=None, visible=True, name=None)`
  — base; `set_mask(mask)` accepts a 2-D grayscale mask (0–255 or 0–1).
- `ImageLayer(image, opacity=1.0, blend_mode='normal', mask=None, visible=True,
  name=None)` — pixel layer (RGB or RGBA). `rgb_alpha()` returns float rgb+alpha.
- `AdjustmentLayer(func, opacity=1.0, mask=None, visible=True, name=None)` —
  non-destructive adjustment; `func: uint8 RGB -> uint8 RGB`, e.g.
  `lambda x: color.brightness(x, 1.2)`. Masked/opacity-scaled.
- `Document(width=None, height=None, background=None)`:
  - `add_layer(layer)`, `add_image(image, **kw) -> ImageLayer`,
    `add_adjustment(func, **kw) -> AdjustmentLayer`.
  - `remove_layer(index)`, `move_layer(index, new_index)`.
  - `render(keep_alpha=False) -> ndarray` — composite. Returns RGBA when
    `keep_alpha=True`, else RGB flattened over `background` (default black).
  - `len(doc)` = number of layers.

---

## CLI — `python -m imgtoolkit <command>`

Subcommands (each prints a clean result; `ImgToolkitError` → stderr message +
exit 1, no traceback):

```
convert  IN OUT [--quality]
resize   IN OUT [--width] [--height] [--no-aspect] [--resample] [--quality]
crop     IN OUT --left --top --right --bottom
rotate   IN OUT --degrees [--no-expand]
flip     IN OUT [--mode h|v]
autoenhance IN OUT
brightness|contrast|saturation IN OUT --factor F
exposure IN OUT --ev EV
hue      IN OUT --degrees D
levels   IN OUT [--in-black --in-white --gamma --out-black --out-white]
curves   IN OUT [--channel] (--points "in,out,in,out" | --points-file file.json)
filter   IN OUT NAME [--radius --angle --distance --amount --strength --seed --color --lut]
         NAME ∈ gaussian motion lens sharpen vignette vintage pencil stylize hdr cartoon oil lut
denoise  IN OUT [--level low|medium|high]
inpaint  IN OUT --mask MASK [--method telea|ns] [--radius]
watermark IN OUT (--text T | --image IMG) [--opacity --position --size --rotation --scale]
strip-metadata IN OUT
exif     IN                       # print EXIF
stitch   IN... -o OUT             # panorama
hdr-merge IN... -o OUT            # exposure-fusion HDR
focus-stack IN... -o OUT [--no-align]
content-aware-scale IN OUT --width W
export   IN OUT (--preset NAME | [--format --quality --strip])
batch    {resize|convert|watermark|strip} IN... --out-dir DIR [--width --height --format --quality --text --image]
```

---

## Dependencies (all permissive / weak-copyleft)

| Package | License | Role |
|---|---|---|
| Pillow | HPND | image I/O, drawing, text |
| numpy | BSD | pixel math |
| opencv-python | Apache-2.0 (wheel MIT) | filters, transforms, inpaint, stitch, HDR |
| scikit-image | BSD | extra algorithms (optional) |
| rawpy | LibRaw (LGPL/CDDL) | RAW loading (guarded import) |
| piexif | MIT | EXIF read/write/strip |

No AGPL, proprietary, or deep-learning model-weight dependencies.
