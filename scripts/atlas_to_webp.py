"""Export a real transparent pose atlas with one shared transform for all frames."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw


def export(args: argparse.Namespace) -> dict:
    if args.columns < 1 or args.rows < 1 or args.size < 16:
        raise ValueError("Grid dimensions must be positive; canvas size must be at least 16.")
    if not 0 < args.fill < 1 or args.repeat < 1 or args.duration_ms < 1:
        raise ValueError("Require 0 < fill < 1, repeat >= 1, duration-ms >= 1.")
    if min(args.first_hold_ms, args.last_hold_ms) < 0:
        raise ValueError("Hold durations must be nonnegative.")
    indices = list(range(args.rows * args.columns)) if args.indices is None else [
        int(x) for x in args.indices.split(",")]
    if not indices or min(indices) < 0 or max(indices) >= args.rows * args.columns:
        raise ValueError("Frame indices must refer to cells in the atlas.")
    destinations = [args.output] + [p for p in (args.gif, args.review) if p]
    resolved = [p.resolve() for p in destinations]
    if len(set(resolved)) != len(resolved) or args.atlas.resolve() in resolved:
        raise ValueError("Input, animation, GIF and review paths must be distinct.")
    with Image.open(args.atlas) as image:
        atlas = image.convert("RGBA")
    if atlas.getchannel("A").getextrema()[0] == 255:
        raise ValueError("Atlas has no actual transparency; regenerate with transparent background.")
    width, height = atlas.size
    if width < args.columns or height < args.rows:
        raise ValueError("Atlas is smaller than its grid.")
    cell_w, cell_h = (width + args.columns - 1) // args.columns, (height + args.rows - 1) // args.rows
    sprites = []
    union = Image.new("L", (cell_w, cell_h))
    for index in indices:
        col, row = index % args.columns, index // args.columns
        box = (round(col * width / args.columns), round(row * height / args.rows),
               round((col + 1) * width / args.columns), round((row + 1) * height / args.rows))
        tile = atlas.crop(box)
        sprite = Image.new("RGBA", (cell_w, cell_h))
        sprite.alpha_composite(tile, (0, 0))
        alpha = sprite.getchannel("A").point(lambda value: 255 if value >= 16 else 0)
        if alpha.getbbox() is None:
            raise ValueError(f"Atlas cell {index} is empty.")
        union = ImageChops.lighter(union, alpha)
        sprites.append(sprite)
    # A shared crop retains the atlas's relative positions and prop contacts.
    bounds = union.getbbox()
    scale = min(args.size * args.fill / (bounds[2] - bounds[0]),
                args.size * args.fill / (bounds[3] - bounds[1]))
    size = (max(1, round((bounds[2] - bounds[0]) * scale)),
            max(1, round((bounds[3] - bounds[1]) * scale)))
    offset = ((args.size - size[0]) // 2, args.size - size[1] - round(args.size * (1 - args.fill) / 2))
    frames = []
    for sprite in sprites * args.repeat:
        frame = Image.new("RGBA", (args.size, args.size))
        frame.alpha_composite(sprite.crop(bounds).resize(size, Image.Resampling.LANCZOS), offset)
        frames.append(frame)
    if len({hashlib.sha256(frame.tobytes()).digest() for frame in frames}) < 2:
        raise ValueError("Selected poses form a static image; at least two different poses are required.")
    durations = [args.duration_ms] * len(frames)
    durations[0] += args.first_hold_ms
    durations[-1] += args.last_hold_ms
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(args.output, format="WEBP", save_all=True, append_images=frames[1:],
                   duration=durations, loop=1, quality=88, method=4)
    total = 0
    with Image.open(args.output) as animation:
        if animation.format != "WEBP" or animation.n_frames < 2 or animation.info.get("loop") != 1:
            raise ValueError("Encoded WebP is not a once-only animation.")
        encoded_frames = animation.n_frames
        for index in range(animation.n_frames):
            animation.seek(index)
            animation.load()
            total += animation.info.get("duration", 0)
            alpha = animation.convert("RGBA").getchannel("A")
            if any(alpha.getpixel(p) for p in ((0, 0), (0, args.size - 1),
                                              (args.size - 1, 0), (args.size - 1, args.size - 1))):
                raise ValueError(f"Opaque animation corner at frame {index}.")
    if total != sum(durations):
        raise ValueError("Encoded WebP duration differs from the planned duration.")
    paper_frames = []
    if args.gif or args.review:
        for frame in frames:
            paper = Image.new("RGB", frame.size, (252, 248, 236))
            paper.paste(frame, (0, 0), frame.getchannel("A"))
            paper_frames.append(paper)
    if args.gif:
        palette_strip = Image.new("RGB", (96 * len(frames), 96))
        for index, frame in enumerate(paper_frames):
            palette_strip.paste(frame.resize((96, 96)), (index * 96, 0))
        palette = palette_strip.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in paper_frames]
        gif_durations = [max(10, d // 10 * 10) for d in durations]
        args.gif.parent.mkdir(parents=True, exist_ok=True)
        indexed[0].save(args.gif, format="GIF", save_all=True, append_images=indexed[1:],
                         duration=gif_durations, disposal=2, optimize=False)
        with Image.open(args.gif) as gif:
            if "loop" in gif.info or gif.n_frames < 2:
                raise ValueError("GIF must stop after its first playback.")
            gif_total = 0
            for index in range(gif.n_frames):
                gif.seek(index)
                gif.load()
                gif_total += gif.info.get("duration", 0)
            if gif_total != sum(gif_durations):
                raise ValueError("GIF duration mismatch.")
    if args.review:
        sheet = Image.new("RGB", (960, 350), (252, 248, 236))
        draw = ImageDraw.Draw(sheet)
        for col, index in enumerate((0, len(sprites) // 2, len(frames) - 1)):
            sheet.paste(paper_frames[index].resize((320, 320)), (col * 320, 30))
            draw.text((col * 320 + 10, 8), f"Frame {index + 1}/{len(frames)}", fill=(48, 75, 53))
        args.review.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.review)
    return {"output": str(args.output.resolve()), "source_frames": len(frames),
            "encoded_frames": encoded_frames, "duration_ms": total, "loop": 1,
            "shared_source_bounds": bounds, "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--indices", help="Zero-based, row-major cell indices separated by commas")
    parser.add_argument("--size", type=int, default=620)
    parser.add_argument("--fill", type=float, default=0.86)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--duration-ms", type=int, default=170)
    parser.add_argument("--first-hold-ms", type=int, default=500)
    parser.add_argument("--last-hold-ms", type=int, default=1000)
    parser.add_argument("--gif", type=Path)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args), ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
