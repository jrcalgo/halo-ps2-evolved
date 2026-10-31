#!/usr/bin/env python3
"""Send test keys to a PCSX2 X11 window using XTest."""

import argparse
import ctypes
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("window", type=lambda value: int(value, 0))
    parser.add_argument("keys", nargs="+")
    args = parser.parse_args()
    x11 = ctypes.CDLL("libX11.so.6")
    xtest = ctypes.CDLL("libXtst.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    display = x11.XOpenDisplay(None)
    if not display:
        parser.error("cannot open X11 display")
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XKeysymToKeycode.restype = ctypes.c_uint
    x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    xtest.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    x11.XSetInputFocus(display, args.window, 1, 0)
    x11.XFlush(display)
    time.sleep(0.2)
    for name in args.keys:
        key = x11.XKeysymToKeycode(display, x11.XStringToKeysym(name.encode()))
        if not key:
            parser.error(f"unknown key: {name}")
        xtest.XTestFakeKeyEvent(display, key, 1, 0)
        x11.XFlush(display)
        time.sleep(0.08)
        xtest.XTestFakeKeyEvent(display, key, 0, 0)
        x11.XFlush(display)
        time.sleep(0.3)
    x11.XCloseDisplay(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
