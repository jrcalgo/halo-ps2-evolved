"""Window-scoped X11 capture and input for the project's visible PCSX2 runs."""
import ctypes
import ctypes.util
import os
from pathlib import Path
import re
import struct
import subprocess
import zlib


def windows(process_group):
    lines = subprocess.check_output(["wmctrl", "-lp"], text=True).splitlines()
    result = []
    for line in lines:
        row = line.split(None, 4)
        try:
            if int(row[2]) > 0 and os.getpgid(int(row[2])) == process_group:
                result.append(row)
        except ProcessLookupError:
            continue
    return result


def focus(window):
    subprocess.run(["wmctrl", "-ia", window], check=True)


def geometry(window):
    text = subprocess.check_output(["xwininfo", "-id", window], text=True)
    return tuple(int(re.search(name + r":\s+(-?\d+)", text).group(1)) for name in
                 ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height"))


def capture(window, destination):
    """Capture one emulator window; no other desktop surface is captured."""
    destination = Path(destination)
    raw_path = destination.with_suffix(".xwd")
    subprocess.run(["xwd", "-silent", "-id", window, "-out", str(raw_path)], check=True)
    raw = raw_path.read_bytes()
    h = struct.unpack_from(">25I", raw)
    if (h[2], h[7], h[14], h[15], h[16]) != (2, 0, 0xFF0000, 0xFF00, 0xFF) or h[11] not in (24, 32):
        raise RuntimeError("Unsupported XWD pixel layout")
    width, height, stride = h[4], h[5], h[12]
    pixel_bytes = h[11] // 8
    pixels = raw[h[0] + 12 * h[19]:]
    rows = []
    for y in range(height):
        source = pixels[y * stride:y * stride + width * pixel_bytes]
        row = bytearray(width * 3)
        row[0::3], row[1::3], row[2::3] = source[2::pixel_bytes], source[1::pixel_bytes], source[0::pixel_bytes]
        rows.append(b"\0" + row)

    def chunk(name, body):
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))

    destination.write_bytes(b"\x89PNG\r\n\x1a\n" +
                            chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0)) +
                            chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    raw_path.unlink()
    return destination


class Input:
    def __init__(self):
        self.x = ctypes.CDLL(ctypes.util.find_library("X11"))
        self.t = ctypes.CDLL(ctypes.util.find_library("Xtst"))
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XKeysymToKeycode.restype = ctypes.c_uint
        self.x.XFlush.argtypes = [ctypes.c_void_p]
        self.x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.t.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.display = self.x.XOpenDisplay(os.environ.get("DISPLAY", ":0.0").encode())
        if not self.display:
            raise RuntimeError("Cannot open the visible desktop display")

    def key(self, name, down):
        code = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(name.encode()))
        if not code:
            raise RuntimeError("Unknown X11 key: " + name)
        self.t.XTestFakeKeyEvent(self.display, code, int(down), 0)
        self.x.XFlush(self.display)

    def click(self, x, y):
        self.t.XTestFakeMotionEvent(self.display, -1, x, y, 0)
        self.t.XTestFakeButtonEvent(self.display, 1, 1, 0)
        self.t.XTestFakeButtonEvent(self.display, 1, 0, 0)
        self.x.XFlush(self.display)

    def close(self):
        if self.display:
            self.x.XCloseDisplay(self.display)
            self.display = None
