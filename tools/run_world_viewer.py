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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("interpreter", "recompiler"), default="recompiler")
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--camera", type=float, nargs=5, default=[65, -95, 9, -70, -5])
    parser.add_argument("--objects", action="store_true")
    args = parser.parse_args()
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
        lines += ["obj bloodgulch.obj.hp2", "objects 1", "sky3d 1", "objanim 0"]
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
    process = subprocess.Popen(command,cwd=ROOT,env={**os.environ,"DISPLAY":config["display"],"QT_QPA_PLATFORM":"xcb","APPIMAGE_EXTRACT_AND_RUN":"1"},stdout=(run/"launcher.log").open("w"),stderr=subprocess.STDOUT,start_new_session=True)
    save(OUTPUT / "active.json",{"pid":process.pid,"run_directory":str(run)})
    print("Visible Blood Gulch viewer; evidence: " + str(run),flush=True)
    start = progress = time.monotonic(); size = 0; window = None
    try:
        while time.monotonic()-start < 3600:
            text = log.read_text(errors="replace") if log.exists() else ""
            if len(text)!=size: size=len(text); progress=time.monotonic()
            if "[err]" in text or " OVERFLOW" in text:
                raise RuntimeError("Viewer reported an error or DMA overflow")
            if window is None:
                owned=windows(process.pid)
                if owned:
                    window=owned[0][0];subprocess.run(["wmctrl","-ir",window,"-e","0,80,80,1024,768"],check=True);focus(window)
            if window and "[prof] frames=" in text and not result["captures"]:
                capture(window,run/"visible-start.png");result["captures"].append(str(run/"visible-start.png"));save(path,result)
            done=re.search(r"\[done\] frames=(\d+) dropped=(\d+)",text)
            if window and done:
                if int(done[1])<args.frames or "[cfg] no host:halo.cfg" in text:
                    raise RuntimeError("Viewer did not execute the requested local scenario")
                time.sleep(.5);capture(window,run/"visible-final.png")
                keyboard=Input();focus(window);keyboard.key("F8",True);time.sleep(.1);keyboard.key("F8",False);keyboard.close()
                result["captures"].append(str(run/"visible-final.png"));result.update(status="diagnostic-completed",frames=int(done[1]),dropped=int(done[2]),wall_seconds=time.monotonic()-start)
                save(path,result);save(OUTPUT/"world-latest.json",result);print("Static viewer diagnostic completed",flush=True);return
            if process.poll() is not None: raise RuntimeError("Viewer exited before scenario completion")
            if time.monotonic()-progress>120: raise RuntimeError("Viewer log progress stopped")
            time.sleep(.25)
        raise RuntimeError("Viewer exceeded wall timeout")
    except Exception as error:
        result.update(status="failed",error=str(error));save(path,result);raise


if __name__ == "__main__":
    try: main()
    except (OSError,RuntimeError,subprocess.SubprocessError) as error: sys.exit(f"World viewer failed: {error}")
