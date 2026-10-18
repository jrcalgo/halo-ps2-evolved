"""Launch the existing static-world viewer visibly; short runs are diagnostics only."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from test_emulator import ROOT, OUTPUT, prepare, stop_previous, sha, save
from test_probe_emulator import require_platform
from emulator_window import windows, focus, capture, Input


# Inside the converted Blood Gulch bounds, with margin. Times are seconds at 30 fps.
ROUTE = [
    (0, 65, -95, 9, -70, -5), (25, 20, -90, 8, -20, -8), (50, 18, -150, 7, 20, -5),
    (75, 70, -175, 8, 80, -4), (100, 120, -160, 10, 10, -6), (125, 118, -70, 12, -160, -8),
    (150, 90, -55, 14, -100, -10), (175, 40, -60, 16, -40, -12), (200, 30, -120, 4, 90, -2),
    (225, 100, -130, 20, -90, -15), (250, 65, -95, 9, -70, -5), (300, 65, -110, 12, -70, -5),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("interpreter", "recompiler"), default="recompiler")
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--camera", type=float, nargs=5, default=[65, -95, 9, -70, -5])
    parser.add_argument("--objects", action="store_true")
    parser.add_argument("--route", action="store_true")
    parser.add_argument("--freecam", action="store_true")
    args = parser.parse_args()
    if args.route:
        args.frames = 9000
        args.objects = True
    if args.freecam:
        args.frames = 3000
        args.objects = True
    if not 60 <= args.frames <= 18000:
        raise RuntimeError("Choose 60 through 18000 frames")
    require_platform()
    report = json.loads((ROOT / "build/world-elf/result.json").read_text())
    original = ROOT / "build/world-elf/world.elf"
    if sha(original) != report["elf_sha256"]:
        raise RuntimeError("World ELF changed after build")
    for name, digest in report["source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rebuild the viewer after changing " + name)
    converted = json.loads((ROOT / "build/convert/bloodgulch.json").read_text())
    packs = ROOT / "data/retail/convert/bloodgulch/run-a"
    suffixes = {"bsp": ".hp2", "textures": ".tex.hp2", "objects": ".obj.hp2"}
    for kind, suffix in suffixes.items():
        if sha(packs / ("bloodgulch" + suffix)) != converted["pack_sha256"][kind]:
            raise RuntimeError("Converted pack hash differs: " + kind)
    stop_previous()
    run = OUTPUT / "runs" / f"world-{args.mode}-{uuid.uuid4().hex}"
    boot = run / "boot"
    boot.mkdir(parents=True)
    elf = boot / "world.elf"
    shutil.copy2(original, elf)
    for suffix in suffixes.values():
        (boot / ("bloodgulch" + suffix)).symlink_to(packs / ("bloodgulch" + suffix))
    lines = ["pack bloodgulch.hp2", "tex bloodgulch.tex.hp2", "arena_mb 12", "textures 1", "lightmaps 1", "clipbudget 1000",
             "camera " + " ".join(map(str,args.camera)), "frames " + str(args.frames), "fps 30", "hold 1", "overlay 1", "printcam 1", "fp 0", "lodctl 0"]
    if args.objects:
        lines += ["obj bloodgulch.obj.hp2", "objects 1", "sky3d 1", "skyfog 1", "objanim 0"]
    if args.route:
        lines += ["pathkey " + " ".join(map(str, key)) for key in ROUTE]
    cfg = boot / "halo.cfg"
    cfg.write_text("\n".join(lines) + "\n")
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    ini = prepare(config, run, args.mode)
    log = run / "emulog.txt"
    command = [config["binary"], "-datapath", str(run / "data"), "-nofullscreen", "-logfile", str(log), "-elf", str(elf)]
    result = {"status":"running", "scenario":"bloodgulch-static", "mode":args.mode, "visible":True, "command":command,
              "elf_sha256":sha(elf), "source_sha256":report["source_sha256"], "pack_sha256":converted["pack_sha256"],
              "settings_sha256":sha(ini), "config_sha256":sha(cfg), "camera":args.camera, "requested_frames":args.frames,
              "bios_sha256":sha(config["bios"]), "emulator_sha256":sha(Path(config["binary"]).resolve()),
              "run_directory":str(run), "log":str(log), "captures":[], "limits":"Diagnostic static viewer; no M10 completion or hardware performance claim."}
    path = run / "result.json"
    save(path,result)
    process = subprocess.Popen(command,cwd=boot,env={**os.environ,"DISPLAY":config["display"],"QT_QPA_PLATFORM":"xcb","APPIMAGE_EXTRACT_AND_RUN":"1"},stdout=(run/"launcher.log").open("w"),stderr=subprocess.STDOUT,start_new_session=True)
    save(OUTPUT / "active.json",{"pid":process.pid,"run_directory":str(run)})
    print("Visible Blood Gulch viewer; evidence: " + str(run),flush=True)
    start = progress = time.monotonic(); size = 0; window = None
    keyboard = Input() if args.freecam else None
    held = ()
    try:
        while time.monotonic()-start < 7200:
            text = log.read_text(errors="replace") if log.exists() else ""
            if len(text)!=size: size=len(text); progress=time.monotonic()
            if "[err]" in text or " OVERFLOW" in text:
                raise RuntimeError("Viewer reported an error or DMA overflow")
            if window is None:
                owned=windows(process.pid)
                if owned:
                    window=owned[0][0];subprocess.run(["wmctrl","-ir",window,"-e","0,80,80,1024,768"],check=True);focus(window)
            if args.freecam and window:
                samples = re.findall(r"\[cam\] pos (-?\d+\.\d+) (-?\d+\.\d+) (-?\d+\.\d+)", text)
                x = float(samples[-1][0]) if samples else 65.0
                y = float(samples[-1][1]) if samples else -95.0
                # Observed on this pad map: W moves toward -Y, S toward +Y. Strafe is chosen after the first X sample.
                mode = getattr(keyboard, "mode", "south")
                origin = getattr(keyboard, "origin", None)
                z = float(samples[-1][2]) if samples else 9.0
                if mode == "south" and y < -165:
                    mode, origin = "north", None
                elif mode == "north" and y > -60:
                    mode, origin = "east", x
                elif mode == "east" and origin is not None and x < origin - 8:
                    mode, origin = "east-a", None
                elif mode in ("east", "east-a") and x > 120:
                    mode, origin = "west", x
                elif mode == "west" and origin is not None and x > origin + 8:
                    mode, origin = "west-d", None
                elif mode in ("west", "west-d") and x < 30:
                    mode, origin = "rise", None
                elif mode == "rise" and z > 20:
                    mode = "done"
                keyboard.mode, keyboard.origin = mode, origin
                keys = {"south": ("W", "3"), "north": ("S", "3"), "east": ("D", "3"), "east-a": ("A", "3"),
                        "west": ("A", "3"), "west-d": ("D", "3"), "rise": ("E", "3"), "done": ()}[mode]
                now = time.monotonic()
                if keys != held or now - getattr(keyboard, "sent", 0) > 2:
                    focus(window)
                    time.sleep(0.2)
                    for key in held:
                        if key not in keys: keyboard.key(key, False)
                    for key in keys:
                        keyboard.key(key, True)
                    held = keys
                    keyboard.sent = now
            if window and "[prof] frames=" in text and not result["captures"]:
                capture(window,run/"visible-start.png");result["captures"].append(str(run/"visible-start.png"));save(path,result)
            if window and args.route and re.search(r"\[prof\] frames=4500 ", text) and len(result["captures"]) == 1:
                capture(window,run/"visible-route.png");result["captures"].append(str(run/"visible-route.png"));save(path,result)
            done=re.search(r"\[done\] frames=(\d+) dropped=(\d+)",text)
            if window and done:
                if int(done[1])<args.frames or "[cfg] no host:halo.cfg" in text:
                    raise RuntimeError("Viewer did not execute the requested local scenario")
                if args.route and ("scripted path: 12 keys" not in text or "sky model: drawn" not in text or "ee prep avg=" not in text or "tex hit=" not in text):
                    raise RuntimeError("Route did not record the scripted camera, sky, or profiler breakdown")
                if args.freecam:
                    positions = [tuple(map(float, values)) for values in re.findall(r"\[cam\] pos (-?\d+\.\d+) (-?\d+\.\d+) (-?\d+\.\d+)", text)]
                    if len(positions) < 8:
                        raise RuntimeError("Free-camera positions were not logged")
                    xs = [position[0] for position in positions]
                    ys = [position[1] for position in positions]
                    zs = [position[2] for position in positions]
                    span = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
                    # Converted BSP extents are about x 6..132, y -190..-45. Require a pad flight that reaches toward each side.
                    if min(xs) > 40 or max(xs) < 110 or min(ys) > -150 or max(ys) < -70 or span[2] < 6:
                        raise RuntimeError("Free camera did not traverse the map bounds: " + str([min(xs), max(xs), min(ys), max(ys), span]))
                    result["camera_span"] = span
                time.sleep(.5);capture(window,run/"visible-final.png")
                focus(window);keyboard_shot=Input();keyboard_shot.key("F8",True);time.sleep(.1);keyboard_shot.key("F8",False);keyboard_shot.close()
                status = "route-completed" if args.route else "freecam-completed" if args.freecam else "diagnostic-completed"
                result["captures"].append(str(run/"visible-final.png"));result.update(status=status,frames=int(done[1]),dropped=int(done[2]),wall_seconds=time.monotonic()-start)
                save(path,result);save(OUTPUT/"world-latest.json",result);print("Static viewer " + status,flush=True);return
            if process.poll() is not None: raise RuntimeError("Viewer exited before scenario completion")
            if time.monotonic()-progress>300: raise RuntimeError("Viewer log progress stopped")
            time.sleep(.25)
        raise RuntimeError("Viewer exceeded wall timeout")
    except Exception as error:
        result.update(status="failed",error=str(error));save(path,result);raise
    finally:
        if keyboard and held:
            for key in held: keyboard.key(key, False)
        if keyboard: keyboard.close()


if __name__ == "__main__":
    try: main()
    except (OSError,RuntimeError,subprocess.SubprocessError) as error: sys.exit(f"World viewer failed: {error}")
