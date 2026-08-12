"""Command-line interface: ``python -m imgtoolkit <command> ...``.

Batch-friendly subcommands wrap the library. On an
:class:`~imgtoolkit.errors.ImgToolkitError` the CLI prints a clean one-line
message to stderr and exits non-zero (no traceback).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from . import (batch, color, effects_advanced, export, filters, io_util,
               metadata, retouch, transform, watermark)
from .errors import ImgToolkitError


def _load(path):
    return io_util.load(path)


def _save(img, path, quality=None):
    out = io_util.save(img, path, quality=quality)
    print(f"wrote {out} ({img.shape[1]}x{img.shape[0]})")


def _expand_inputs(patterns):
    """Expand glob patterns / directories into a sorted list of files."""
    files = []
    for p in patterns:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "*"))))
        else:
            matched = sorted(glob.glob(p))
            files.extend(matched if matched else [p])
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise ImgToolkitError("no input files matched")
    return files


# ---------------------------------------------------------------------------
# Command handlers. Each takes parsed args and does its work.
# ---------------------------------------------------------------------------

def cmd_convert(a):
    img = _load(a.input)
    _save(img, a.output, quality=a.quality)


def cmd_resize(a):
    img = _load(a.input)
    img = transform.resize(img, a.width, a.height, keep_aspect=not a.no_aspect,
                           resample=a.resample)
    _save(img, a.output, quality=a.quality)


def cmd_crop(a):
    img = _load(a.input)
    img = transform.crop(img, (a.left, a.top, a.right, a.bottom))
    _save(img, a.output, quality=a.quality)


def cmd_rotate(a):
    img = _load(a.input)
    img = transform.rotate(img, a.degrees, expand=not a.no_expand)
    _save(img, a.output, quality=a.quality)


def cmd_flip(a):
    img = _load(a.input)
    img = transform.flip(img, a.mode)
    _save(img, a.output, quality=a.quality)


def cmd_autoenhance(a):
    img = _load(a.input)
    img = color.auto_enhance(img)
    _save(img, a.output, quality=a.quality)


def cmd_brightness(a):
    _save(color.brightness(_load(a.input), a.factor), a.output, a.quality)


def cmd_contrast(a):
    _save(color.contrast(_load(a.input), a.factor), a.output, a.quality)


def cmd_exposure(a):
    _save(color.exposure(_load(a.input), a.ev), a.output, a.quality)


def cmd_saturation(a):
    _save(color.saturation(_load(a.input), a.factor), a.output, a.quality)


def cmd_hue(a):
    _save(color.hue_shift(_load(a.input), a.degrees), a.output, a.quality)


def cmd_levels(a):
    img = color.levels(_load(a.input), a.in_black, a.in_white, a.gamma,
                       a.out_black, a.out_white)
    _save(img, a.output, a.quality)


def cmd_curves(a):
    if a.points_file:
        with open(a.points_file) as fh:
            pts = json.load(fh)
    elif a.points:
        nums = [float(x) for x in a.points.replace(";", ",").split(",")]
        pts = list(zip(nums[0::2], nums[1::2]))
    else:
        raise ImgToolkitError("curves needs --points or --points-file")
    _save(color.curves(_load(a.input), a.channel, pts), a.output, a.quality)


_FILTERS = {
    "gaussian": lambda img, a: filters.gaussian_blur(img, a.radius),
    "motion": lambda img, a: filters.motion_blur(img, a.angle, int(a.distance)),
    "lens": lambda img, a: filters.lens_blur(img, int(a.radius)),
    "sharpen": lambda img, a: filters.sharpen(img, a.amount, a.radius),
    "vignette": lambda img, a: filters.vignette(img, a.strength),
    "vintage": lambda img, a: filters.vintage(img, seed=a.seed),
    "pencil": lambda img, a: filters.pencil_sketch(img, color=a.color),
    "stylize": lambda img, a: filters.stylize(img),
    "hdr": lambda img, a: filters.hdr_effect(img, a.strength),
    "cartoon": lambda img, a: filters.cartoon(img),
    "oil": lambda img, a: filters.oil_paint(img),
    "lut": lambda img, a: filters.apply_lut(img, a.lut),
}


def cmd_filter(a):
    if a.name not in _FILTERS:
        raise ImgToolkitError(f"unknown filter '{a.name}'; "
                              f"choose from {sorted(_FILTERS)}")
    if a.name == "lut" and not a.lut:
        raise ImgToolkitError("filter lut needs --lut path.cube")
    img = _FILTERS[a.name](_load(a.input), a)
    _save(img, a.output, a.quality)


def cmd_denoise(a):
    _save(retouch.reduce_noise(_load(a.input), a.level), a.output, a.quality)


def cmd_inpaint(a):
    img = _load(a.input)
    mask = io_util.load(a.mask)
    img = retouch.object_removal(img, mask, method=a.method, radius=a.radius)
    _save(img, a.output, a.quality)


def cmd_watermark(a):
    img = _load(a.input)
    if a.text:
        img = watermark.text_watermark(img, a.text, opacity=a.opacity,
                                       position=a.position, size=a.size,
                                       rotation=a.rotation)
    elif a.image:
        img = watermark.image_watermark(img, a.image, opacity=a.opacity,
                                        position=a.position, scale=a.scale)
    else:
        raise ImgToolkitError("watermark needs --text or --image")
    _save(img, a.output, a.quality)


def cmd_strip_metadata(a):
    out = metadata.strip_metadata(a.input, a.output)
    print(f"stripped metadata -> {out}")


def cmd_exif(a):
    data = metadata.read_exif(a.input)
    if not data:
        print("(no EXIF)")
    else:
        for k, v in data.items():
            print(f"{k}: {v}")


def cmd_stitch(a):
    imgs = [io_util.load(p) for p in _expand_inputs(a.inputs)]
    pano = effects_advanced.panorama_stitch(imgs)
    _save(pano, a.output, a.quality)


def cmd_hdr_merge(a):
    imgs = [io_util.load(p) for p in _expand_inputs(a.inputs)]
    out = effects_advanced.hdr_merge(imgs)
    _save(out, a.output, a.quality)


def cmd_focus_stack(a):
    imgs = [io_util.load(p) for p in _expand_inputs(a.inputs)]
    out = effects_advanced.focus_stack(imgs, align=not a.no_align)
    _save(out, a.output, a.quality)


def cmd_content_aware_scale(a):
    img = _load(a.input)
    out = effects_advanced.content_aware_scale(img, a.width)
    _save(out, a.output, a.quality)


def cmd_export(a):
    img = _load(a.input)
    if a.preset:
        out = export.export_preset(img, a.output, a.preset)
    else:
        out = export.export(img, a.output, fmt=a.format, quality=a.quality,
                            strip_metadata=a.strip)
    print(f"exported -> {out}")


def cmd_batch(a):
    inputs = _expand_inputs(a.inputs)
    if a.op == "resize":
        written = batch.batch_resize(inputs, a.out_dir, width=a.width,
                                     height=a.height, out_format=a.format,
                                     quality=a.quality)
    elif a.op == "convert":
        if not a.format:
            raise ImgToolkitError("batch convert needs --format")
        written = batch.batch_convert(inputs, a.out_dir, a.format,
                                      quality=a.quality)
    elif a.op == "watermark":
        written = batch.batch_watermark(inputs, a.out_dir, text=a.text,
                                        overlay_path=a.image,
                                        out_format=a.format, quality=a.quality)
    elif a.op == "strip":
        written = batch.batch_strip_metadata(inputs, a.out_dir)
    else:
        raise ImgToolkitError(f"unknown batch op '{a.op}'")
    print(f"wrote {len(written)} files to {a.out_dir}")
    for w in written:
        print(f"  {w}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="imgtoolkit",
        description="Headless image-editing toolkit (Apache-2.0).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def io_args(sp, quality=True):
        sp.add_argument("input")
        sp.add_argument("output")
        if quality:
            sp.add_argument("--quality", type=int, default=None)

    sp = sub.add_parser("convert", help="convert format")
    io_args(sp); sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("resize", help="resize image")
    io_args(sp)
    sp.add_argument("--width", type=int)
    sp.add_argument("--height", type=int)
    sp.add_argument("--no-aspect", action="store_true", help="ignore aspect ratio")
    sp.add_argument("--resample", default="auto")
    sp.set_defaults(func=cmd_resize)

    sp = sub.add_parser("crop", help="crop to box")
    io_args(sp)
    for name in ("left", "top", "right", "bottom"):
        sp.add_argument(f"--{name}", type=int, required=True)
    sp.set_defaults(func=cmd_crop)

    sp = sub.add_parser("rotate", help="rotate degrees CCW")
    io_args(sp)
    sp.add_argument("--degrees", type=float, required=True)
    sp.add_argument("--no-expand", action="store_true")
    sp.set_defaults(func=cmd_rotate)

    sp = sub.add_parser("flip", help="flip h/v")
    io_args(sp)
    sp.add_argument("--mode", choices=["h", "v"], default="h")
    sp.set_defaults(func=cmd_flip)

    sp = sub.add_parser("autoenhance", help="one-click enhance")
    io_args(sp); sp.set_defaults(func=cmd_autoenhance)

    sp = sub.add_parser("brightness"); io_args(sp)
    sp.add_argument("--factor", type=float, required=True)
    sp.set_defaults(func=cmd_brightness)

    sp = sub.add_parser("contrast"); io_args(sp)
    sp.add_argument("--factor", type=float, required=True)
    sp.set_defaults(func=cmd_contrast)

    sp = sub.add_parser("exposure"); io_args(sp)
    sp.add_argument("--ev", type=float, required=True)
    sp.set_defaults(func=cmd_exposure)

    sp = sub.add_parser("saturation"); io_args(sp)
    sp.add_argument("--factor", type=float, required=True)
    sp.set_defaults(func=cmd_saturation)

    sp = sub.add_parser("hue"); io_args(sp)
    sp.add_argument("--degrees", type=float, required=True)
    sp.set_defaults(func=cmd_hue)

    sp = sub.add_parser("levels"); io_args(sp)
    sp.add_argument("--in-black", type=float, default=0)
    sp.add_argument("--in-white", type=float, default=255)
    sp.add_argument("--gamma", type=float, default=1.0)
    sp.add_argument("--out-black", type=float, default=0)
    sp.add_argument("--out-white", type=float, default=255)
    sp.set_defaults(func=cmd_levels)

    sp = sub.add_parser("curves"); io_args(sp)
    sp.add_argument("--channel", default="rgb")
    sp.add_argument("--points", help="comma list: in,out,in,out,...")
    sp.add_argument("--points-file", help="JSON list of [in,out] pairs")
    sp.set_defaults(func=cmd_curves)

    sp = sub.add_parser("filter", help="apply a named filter")
    io_args(sp)
    sp.add_argument("name", help="gaussian/motion/lens/sharpen/vignette/"
                                 "vintage/pencil/stylize/hdr/cartoon/oil/lut")
    sp.add_argument("--radius", type=float, default=3.0)
    sp.add_argument("--angle", type=float, default=0.0)
    sp.add_argument("--distance", type=float, default=15)
    sp.add_argument("--amount", type=float, default=1.0)
    sp.add_argument("--strength", type=float, default=0.6)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--color", action="store_true")
    sp.add_argument("--lut", help=".cube LUT path (for filter lut)")
    sp.set_defaults(func=cmd_filter)

    sp = sub.add_parser("denoise"); io_args(sp)
    sp.add_argument("--level", choices=["low", "medium", "high"], default="medium")
    sp.set_defaults(func=cmd_denoise)

    sp = sub.add_parser("inpaint", help="classical inpaint under a mask")
    io_args(sp)
    sp.add_argument("--mask", required=True, help="mask image (non-zero=fill)")
    sp.add_argument("--method", choices=["telea", "ns"], default="telea")
    sp.add_argument("--radius", type=int, default=10)
    sp.set_defaults(func=cmd_inpaint)

    sp = sub.add_parser("watermark"); io_args(sp)
    sp.add_argument("--text")
    sp.add_argument("--image", help="overlay image path")
    sp.add_argument("--opacity", type=float, default=0.5)
    sp.add_argument("--position", default="bottom-right")
    sp.add_argument("--size", type=int, default=32)
    sp.add_argument("--rotation", type=float, default=0.0)
    sp.add_argument("--scale", type=float, default=0.2)
    sp.set_defaults(func=cmd_watermark)

    sp = sub.add_parser("strip-metadata")
    sp.add_argument("input"); sp.add_argument("output")
    sp.set_defaults(func=cmd_strip_metadata)

    sp = sub.add_parser("exif", help="print EXIF")
    sp.add_argument("input")
    sp.set_defaults(func=cmd_exif)

    sp = sub.add_parser("stitch", help="panorama stitch")
    sp.add_argument("inputs", nargs="+")
    sp.add_argument("--output", "-o", required=True)
    sp.add_argument("--quality", type=int, default=None)
    sp.set_defaults(func=cmd_stitch)

    sp = sub.add_parser("hdr-merge", help="exposure-fusion HDR merge")
    sp.add_argument("inputs", nargs="+")
    sp.add_argument("--output", "-o", required=True)
    sp.add_argument("--quality", type=int, default=None)
    sp.set_defaults(func=cmd_hdr_merge)

    sp = sub.add_parser("focus-stack", help="focus stacking")
    sp.add_argument("inputs", nargs="+")
    sp.add_argument("--output", "-o", required=True)
    sp.add_argument("--no-align", action="store_true")
    sp.add_argument("--quality", type=int, default=None)
    sp.set_defaults(func=cmd_focus_stack)

    sp = sub.add_parser("content-aware-scale", help="seam-carve width")
    io_args(sp)
    sp.add_argument("--width", type=int, required=True)
    sp.set_defaults(func=cmd_content_aware_scale)

    sp = sub.add_parser("export", help="export with preset or explicit opts")
    io_args(sp)
    sp.add_argument("--preset", help=f"one of {export.list_presets()}")
    sp.add_argument("--format")
    sp.add_argument("--strip", action="store_true")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("batch", help="batch resize/convert/watermark/strip")
    sp.add_argument("op", choices=["resize", "convert", "watermark", "strip"])
    sp.add_argument("inputs", nargs="+")
    sp.add_argument("--out-dir", required=True)
    sp.add_argument("--width", type=int)
    sp.add_argument("--height", type=int)
    sp.add_argument("--format")
    sp.add_argument("--quality", type=int, default=None)
    sp.add_argument("--text")
    sp.add_argument("--image")
    sp.set_defaults(func=cmd_batch)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except ImgToolkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
