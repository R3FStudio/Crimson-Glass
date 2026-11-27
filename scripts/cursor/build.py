#!/usr/bin/python3
import argparse
import math
from pathlib import Path
import subprocess
import tempfile

import cairo
import gi
from stock import build_stock

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg


SIZES = (24, 32, 36, 48, 64, 72, 96, 144)
FRAME_COUNT = 20
FRAME_DELAY = 135

POINTERS = {
    "default": {
        "shape": "M 7 5 L 37 25 L 23.2 26.7 L 29.7 39.3 L 22.1 43 L 15.7 30.3 L 8.2 37.4 Z",
        "accent": "M 25.7 38.5 L 20.4 28.1 Q 19.6 26.5 20.9 25.2 L 22.6 23.8",
        "glint": "M 12.1 11.9 L 28.8 23.1",
        "hotspot": (7, 5),
        "aliases": ("left_ptr", "arrow", "top_left_arrow"),
    },
    "pointer": {
        "shape": "M 17 27 L 17 9 C 17 6.5 18.5 5 20.7 5 C 23 5 24.4 6.5 24.4 9 "
                 "L 24.4 18.2 C 25.7 16.6 28.9 16.7 30.4 19 C 32.5 18.3 34.8 19.1 36 21.4 "
                 "C 39.8 21.5 41 24.8 40.8 28.1 L 40.1 34.4 "
                 "Q 39.7 38 36.3 40.4 L 36.3 43 L 23 43 L 23 40.1 "
                 "Q 20.5 38.5 18.8 35.9 L 11.2 28.3 C 9.6 26.6 9.7 24.6 11.2 23.4 "
                 "C 12.5 22.4 14.2 22.8 15.5 24 Z",
        "accent": "M 24.7 35.9 Q 29.2 38.9 35.1 35.9",
        "glint": "M 20.6 9.4 L 20.6 19.8",
        "hotspot": (20, 5),
        "aliases": ("hand2", "pointing_hand", "e29285e634086352946a0e7090d73106"),
    },
}


def artwork(pointer, frame):
    pulse = 0.5 - 0.5 * math.cos(math.tau * frame / FRAME_COUNT)
    rim_angle = 360 * frame / FRAME_COUNT
    shape = pointer["shape"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
      <defs>
        <linearGradient id="crimson" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#fb677c"/>
          <stop offset="100%" stop-color="#cb1548"/>
        </linearGradient>
        <linearGradient id="rim" x1="0%" y1="0%" x2="100%" y2="100%"
                        gradientTransform="rotate({rim_angle} .5 .5)">
          <stop offset="0%" stop-color="#df173c"/>
          <stop offset="46%" stop-color="#ff435d"/>
          <stop offset="72%" stop-color="#ff99a9"/>
          <stop offset="100%" stop-color="#f42747"/>
        </linearGradient>
      </defs>
      <g stroke-linejoin="round" stroke-linecap="round">
        <path d="{shape}" fill="none" stroke="#e82b60" stroke-opacity="{0.21 + pulse * 0.16:.3f}" stroke-width="4.9"/>
        <path d="{shape}" fill="#000000" stroke="#ffd4dc" stroke-width="3.9"/>
        <path d="{shape}" fill="#000000" stroke="url(#rim)" stroke-width="3.1"/>
        <path d="{pointer['glint']}" fill="none" stroke="#ad7384" stroke-opacity=".52" stroke-width="1.1"/>
        <path d="{pointer['accent']}" fill="none" stroke="#ff7894" stroke-opacity="{0.12 + pulse * 0.26:.3f}" stroke-width="4.2"/>
        <path d="{pointer['accent']}" fill="none" stroke="url(#crimson)" stroke-opacity="{0.65 + pulse * 0.35:.3f}" stroke-width="2.1"/>
      </g>
    </svg>"""


def render(svg, size, path):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    view = Rsvg.Rectangle()
    view.width = size
    view.height = size
    Rsvg.Handle.new_from_data(svg.encode()).render_document(cairo.Context(surface), view)
    surface.write_to_png(str(path))


def build(output):
    cursors = output / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    (output / "index.theme").write_text(
        "[Icon Theme]\nName=Crimson Pulse\n"
        "Comment=High-contrast cursor with a slow crimson accent pulse\n"
        "Inherits=Adwaita\n", encoding="utf-8"
    )
    with tempfile.TemporaryDirectory(prefix="crimson-cursor-") as temp_dir:
        temp = Path(temp_dir)
        for name, pointer in POINTERS.items():
            frames = [artwork(pointer, frame) for frame in range(FRAME_COUNT)]
            config = []
            for size in SIZES:
                x, y = (round(coord * size / 48) for coord in pointer["hotspot"])
                for frame, svg in enumerate(frames):
                    file = temp / f"{size}-{frame}.png"
                    render(svg, size, file)
                    config.append(f"{size} {x} {y} {file} {FRAME_DELAY}")
            subprocess.run(
                ["xcursorgen", "-", str(cursors / name)],
                input="\n".join(config) + "\n", text=True, check=True
            )
            for alias in pointer["aliases"]:
                link = cursors / alias
                link.unlink(missing_ok=True)
                link.symlink_to(name)
    build_stock(cursors, POINTERS, FRAME_COUNT, FRAME_DELAY)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
