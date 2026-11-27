import math
from pathlib import Path
import struct

import numpy as np


ADWAITA = Path("/usr/share/icons/Adwaita/cursors")
IMAGE = 0xFFFD0002
BUSY = {"wait", "progress"}
DETAIL_CURSORS = {
    "alias", "context-menu", "copy", "help", "no-drop", "not-allowed",
    "zoom-in", "zoom-out",
}
LEGACY = {
    "ibeam": "text", "vertical_text": "vertical-text",
    "openhand": "grab", "closedhand": "grabbing",
    "size_all": "all-resize", "sizing": "all-resize",
    "size_hor": "ew-resize", "h_double_arrow": "ew-resize",
    "size_ver": "ns-resize", "v_double_arrow": "ns-resize",
    "size_bdiag": "nesw-resize", "size_fdiag": "nwse-resize",
    "split_h": "col-resize", "split_v": "row-resize",
    "plus": "cell", "circle": "not-allowed", "crossed_circle": "not-allowed",
    "forbidden": "no-drop", "dnd-no-drop": "no-drop",
    "dnd-copy": "copy", "dnd-link": "alias", "link": "alias",
    "left_ptr_help": "help", "whats_this": "help",
    "00008160000006810000408080010102": "ns-resize",
    "03b6e0fcb3499374a867c041f52298f0": "not-allowed",
    "1081e37283d90000800003c07f3ef6bf": "copy",
    "3085a0e285430894940527032f8b26df": "alias",
    "4498f0e0c1937ffe01fd06f973665830": "dnd-move",
    "5c6cd98b3f3ebcb1f9c7f1c204630408": "help",
    "6407b0e94181790501fd1e167b474872": "copy",
    "640fb0e74195791501fd1ed57b41487f": "alias",
    "9081237383d90e509aa00f00170e968f": "dnd-move",
    "9d800788f1b08800ae810202380a0822": "pointer",
    "a2a266d0498c3104214a47bd64ab0fc8": "alias",
    "b66166c04f8c3109214a4fbd64a50fc8": "copy",
    "d9ce0ab605698f320427677b458ad60b": "help",
    "fcf21c00b30f7e3f83fe0dfd12e71cff": "dnd-move",
}
BUSY_ALIASES = (
    "left_ptr_watch", "half-busy", "00000000000000020006000e7e9ffc3f",
    "08e8e1c95fe2fc01f976f1e063a24ccd", "3ecb610c1bf2410f44200f48c40d3599",
)


def images(path):
    data = path.read_bytes()
    magic, header, _, count = struct.unpack_from("<4I", data)
    if magic != 0x72756358:
        raise ValueError(f"{path} is not an Xcursor file")
    for index in range(count):
        kind, size, offset = struct.unpack_from("<3I", data, header + 12 * index)
        if kind != IMAGE:
            continue
        chunk, _, _, _, width, height, xhot, yhot, _ = struct.unpack_from("<9I", data, offset)
        pixels = np.frombuffer(data, dtype=np.uint8, offset=offset + chunk,
                               count=width * height * 4).reshape(height, width, 4)
        yield size, xhot, yhot, pixels


def distance_to_edge(alpha, radius):
    # Keep the stock silhouette and antialiasing. Find the inner edge in the
    # alpha mask so the outline stays narrow on both thin and wide shapes.
    height, width = alpha.shape
    pad = math.ceil(radius + 1)
    outside = np.pad(alpha < 128, pad, constant_values=True)
    distance = np.full(alpha.shape, np.inf)
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            offset = math.hypot(dx, dy)
            if offset <= radius + 1:
                exterior = outside[pad + dy:pad + dy + height, pad + dx:pad + dx + width]
                np.minimum(distance, np.where(exterior, offset, np.inf), out=distance)
    return distance


def tint_frames(pixels, size, count, preserve_symbols):
    alpha = pixels[:, :, 3]
    scale = size / 48
    radius = 1.45 * scale
    distance = distance_to_edge(alpha, max(radius, 2.75 * scale if preserve_symbols else radius))
    edge = np.clip(radius + 0.5 - distance, 0, 1)
    if preserve_symbols:
        # The zoom signs and badges are painted inside an opaque shape.
        # Recover the stock light marks so they remain recognizable.
        light = pixels[:, :, :3].max(axis=2) / np.maximum(alpha, 1)
        detail = np.clip((light - 0.26) / 0.58, 0, 1)
        detail *= np.clip(distance / scale - 1.65, 0, 1)
        edge = np.maximum(edge, detail)
    weight = edge * (alpha / 255)
    height, width = alpha.shape
    yy, xx = np.indices(alpha.shape)
    direction = np.arctan2(yy - (height - 1) / 2, xx - (width - 1) / 2)
    frame = np.zeros_like(pixels)
    frame[:, :, 3] = alpha
    for i in range(count):
        highlight = (0.5 + 0.5 * np.cos(direction - math.tau * i / count)) ** 3
        for channel, base, peak in ((0, 77, 153), (1, 43, 130), (2, 241, 255)):
            frame[:, :, channel] = np.rint((base + (peak - base) * highlight) * weight)
        yield frame.tobytes()


def animate(source, dest, count, delay):
    chunks = []
    for size, xhot, yhot, pixels in images(source):
        height, width, _ = pixels.shape
        header = struct.pack("<9I", 36, IMAGE, size, 1, width, height, xhot, yhot, delay)
        frames = tint_frames(pixels, size, count, source.name in DETAIL_CURSORS)
        chunks.extend((size, header + frame) for frame in frames)

    with dest.open("wb") as out:
        out.write(struct.pack("<4I", 0x72756358, 16, 0x10000, len(chunks)))
        offset = 16 + 12 * len(chunks)
        for size, chunk in chunks:
            out.write(struct.pack("<3I", IMAGE, size, offset))
            offset += len(chunk)
        for _, chunk in chunks:
            out.write(chunk)


def link(path, target):
    path.unlink(missing_ok=True)
    path.symlink_to(target)


def build_stock(cursors, custom, count, delay):
    for path in sorted(ADWAITA.iterdir()):
        if path.name in custom or path.name in BUSY or not path.is_file():
            continue
        if path.is_symlink():
            if path.resolve().name not in BUSY:
                link(cursors / path.name, path.resolve().name)
        else:
            animate(path, cursors / path.name, count, delay)
    for name, target in LEGACY.items():
        link(cursors / name, target)
    for name in BUSY_ALIASES:
        link(cursors / name, ADWAITA / "progress")
