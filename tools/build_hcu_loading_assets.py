#!/usr/bin/env python3
"""Extract the retail Halo CE loading screen from a user-owned Xbox XISO for the PS2 loading screen.

The disc has no loading image file. The picture and the monk chant that plays behind it are compiled into default.xbe
(CE source/interface/progress_bar.c: `progress_bar_load_loading_texture` and `compressed_monk_tone`), so this tool
reads them out of the XBE:

  picture  an 8 byte header (width, height as 16 bit, each followed by 16 bits of zero: 320, 240), then run-length
           coded 4 bit levels: a byte is run << 4 | level, the level scaled to 8 bits (level << 4). The retail loader
           expands a level v into a D3DFMT_LIN_A8B8G8R8 texel with blue v, green v >> 1, red v >> 2, so the picture is
           the edge-lit Halo ring and "LOADING..." in blue. The runs add up to 320 x 240 exactly.
  chant    1.48 s of mono Xbox ADPCM (22050 Hz, 36 byte blocks of 64 samples) straight after the picture, 4 byte aligned
           (18396 bytes): four looping DirectSound voices at different pitches play it during the load.

Nothing here embeds retail bytes: the picture is found by its header and by the run total, the chant by where the
picture ends. The outputs are derived data and are never committed.

  load.rgb          512 x 448 RGB5A1 (the PS2 field), read by src/stream/hcu_loading_screen.c
  load.rgb.stamp    the generator version and the SHA-256 of the picture and chant it was built from
  loading_chant.wav (optional) the decoded chant
  loading_retail.png (optional) the picture at its native 320 x 240
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules" / "halo-ps2" / "tools"))
sys.path.insert(0, str(ROOT / "submodules" / "halo-64"))

VERSION = 2
PICTURE_W, PICTURE_H = 320, 240
HEADER = struct.pack("<HHHH", PICTURE_W, 0, PICTURE_H, 0)
CHANT_BYTES = 18396           # sizeof(compressed_monk_tone)
CHANT_RATE = 22050
SEARCH_WINDOW = 0x10000       # the chant follows the picture; its encoding is under 64 KiB
OUT_W, OUT_H = 512, 448       # the PS2 field


class RetailLoadingError(ValueError):
    pass


def decode_picture(data: bytes) -> tuple[list[int], int]:
    """Run-length decode the picture's 8 bit levels. Returns (levels, bytes used); raises when the runs do not stop at
    exactly PICTURE_W * PICTURE_H."""
    total = PICTURE_W * PICTURE_H
    levels: list[int] = []
    for used, byte in enumerate(data, 1):
        levels.extend([(byte & 15) << 4] * (byte >> 4))
        if len(levels) == total:
            return levels, used
        if len(levels) > total:
            break
    raise RetailLoadingError("run lengths do not add up to the loading picture size")


def valid_chant(raw: bytes) -> bool:
    """Every Xbox ADPCM mono block starts with an int16 predictor, a step index (0..88) and a zero pad byte."""
    if len(raw) != CHANT_BYTES or CHANT_BYTES % 36:
        return False
    return all(raw[at + 2] <= 88 and raw[at + 3] == 0 for at in range(0, CHANT_BYTES, 36))


def locate(xbe: bytes) -> tuple[list[int], bytes]:
    """The picture's levels and the chant's ADPCM bytes inside default.xbe."""
    start = 0
    while True:
        at = xbe.find(HEADER, start)
        if at < 0:
            raise RetailLoadingError("no loading picture in default.xbe: this is not the retail Halo CE XBE")
        start = at + 1
        try:
            levels, used = decode_picture(xbe[at + len(HEADER):at + len(HEADER) + SEARCH_WINDOW])
        except RetailLoadingError:
            continue
        # the chant follows the picture after a little zero padding (the compiler aligns the array)
        end = at + len(HEADER) + used
        for chant_at in range(end, end + 16):
            chant = xbe[chant_at:chant_at + CHANT_BYTES]
            if valid_chant(chant):
                return levels, chant


def picture_image(levels: list[int]):
    """The picture as the retail texture shows it: blue v, green v >> 1, red v >> 2."""
    from PIL import Image
    image = Image.new("RGB", (PICTURE_W, PICTURE_H))
    image.putdata([(v >> 2, (v & 0xFE) >> 1, v) for v in levels])
    return image


def ps2_field(image):
    """The picture stretched over the whole 512 x 448 field, as retail stretches 320 x 240 over the whole screen."""
    from PIL import Image
    return image.resize((OUT_W, OUT_H), Image.Resampling.LANCZOS)


def chant_pcm(raw: bytes) -> list[int]:
    from hcu_sound_bank import decode_xbox_adpcm
    return decode_xbox_adpcm(raw)


def build(xbe: bytes) -> tuple[bytes, bytes, list[int], object]:
    """(load.rgb bytes, stamp, chant pcm, native picture)."""
    from build_hcu_menu_assets import rgb5a1
    levels, chant = locate(xbe)
    native = picture_image(levels)
    packed = rgb5a1(ps2_field(native).convert("RGBA"))
    if len(packed) != OUT_W * OUT_H * 2:
        raise RetailLoadingError("unexpected loading image size")
    digest = hashlib.sha256(bytes(levels) + chant).hexdigest()
    stamp = f"loading-assets v{VERSION} sha256 {digest}\n".encode()
    return packed, stamp, chant_pcm(chant), native


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("iso", type=Path, help="Halo CE Xbox XISO")
    parser.add_argument("output", type=Path, help="load.rgb to write")
    parser.add_argument("--chant-wav", type=Path, help="also write the decoded chant")
    parser.add_argument("--preview", type=Path, help="also write the native 320x240 picture as a PNG")
    args = parser.parse_args()
    from tools.n64.xiso import XboxDisc
    with tempfile.TemporaryDirectory(prefix="hcu-loading-") as folder:
        xbe_path = Path(folder) / "default.xbe"
        disc = XboxDisc(args.iso)
        try:
            disc.extract("default.xbe", xbe_path)
        finally:
            disc.close()
        packed, stamp, pcm, native = build(xbe_path.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.chmod(0o644)
    args.output.write_bytes(packed)
    stamp_path = stamp_for(args.output)
    stamp_path.write_bytes(stamp)
    if args.chant_wav:
        with wave.open(str(args.chant_wav), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(CHANT_RATE)
            out.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))
    if args.preview:
        native.save(args.preview)
    print(f"{args.output}: {len(packed)} bytes ({PICTURE_W}x{PICTURE_H} retail picture -> {OUT_W}x{OUT_H}), "
          f"chant {len(pcm) / CHANT_RATE:.2f}s; {stamp.decode().strip()}")
    return 0


def stamp_for(package: Path) -> Path:
    return package.with_name(package.name + ".stamp")


def current(package: Path) -> bool:
    """A cached load.rgb made by this version of the generator (an older invented backplate has no stamp)."""
    stamp = stamp_for(package)
    try:
        return package.is_file() and stamp.read_text().startswith(f"loading-assets v{VERSION} ")
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
