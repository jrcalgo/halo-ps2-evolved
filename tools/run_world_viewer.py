"""Launch the existing static-world viewer visibly; short runs are diagnostics only."""
import argparse
import configparser
import json
import math
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
# Perimeter views stay above the BSP's ~26-unit maximum and face inward.
# The initial/final valley view is the independently checked reference camera.
ROUTE = [(0,65,-95,9,-70,-5)]
for t,x,y in ((25,65,-145),(50,65,-175),(75,110,-155),(100,118,-105),
              (125,100,-65),(150,65,-58),(175,25,-75),(200,18,-115),(225,30,-155)):
    dx,dy = 68-x,-117-y
    ROUTE.append((t,x,y,32,round(math.degrees(math.atan2(dy,dx)),3),
                  round(math.degrees(math.atan2(4-32,math.hypot(dx,dy))),3)))
ROUTE += [(250,65,-95,9,-70,-5),(300,65,-95,9,-70,-5)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("interpreter", "recompiler"), default="recompiler")
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--camera", type=float, nargs=5, default=[65, -95, 9, -70, -5])
    parser.add_argument("--objects", action="store_true")
    parser.add_argument("--variant", choices=("conservative","portal","stream"), default="conservative")
    parser.add_argument("--force-conservative", action="store_true")
    parser.add_argument("--framebuffer", action="store_true", help="Retain raw GS pixels at frame 120, with HUD disabled")
    parser.add_argument("--route", action="store_true")
    parser.add_argument("--freecam", action="store_true")
    parser.add_argument("--motion", type=Path, default=None,
                        help="pathkey file from the player eye: seconds x y z yaw pitch")
    parser.add_argument("--play", action="store_true",
                        help="leave the window open for keyboard play; do not wait for the frame limit")
    parser.add_argument("--freecam-toggle", action="store_true",
                        help="with --play, press R3/4 once to toggle in-game freecam; press 4 again to return to player control")
    parser.add_argument("--combat-smoke", action="store_true",
                        help="bounded EE pistol-to-vitality diagnostic against the fixed play probe")
    parser.add_argument("--actor-ray-smoke", action="store_true",
                        help="fire one retail shotgun burst through the cyborg mesh and measure per-tick actor-ray work")
    parser.add_argument("--actor-pistol-smoke", action="store_true",
                        help="fire the retail pistol at the live scenario biped until its tag-profiled vitality reaches death")
    parser.add_argument("--actor-ar-smoke", action="store_true",
                        help="sustain retail assault-rifle fire into the live biped and record simulation-tick cadence/ammo")
    parser.add_argument("--shotgun-reload-smoke", action="store_true",
                        help="empty the retail shotgun, release fire, and validate each integrated shell reload tick")
    parser.add_argument("--grenade-smoke", action="store_true",
                        help="bounded EE frag throw, BSP bounce/fuse and blast diagnostic")
    parser.add_argument("--fuel-still", action="store_true",
                        help="play build, start on the fuel rod, dump one GS frame, then exit")
    parser.add_argument("--cache-pages", type=int, default=0,
                        help="diagnostic-only stream cache cap")
    parser.add_argument("--cache-route", action="store_true",
                        help="sweep fixed Blood Gulch views in the stream diagnostic")
    parser.add_argument("--framebuffer-frame", type=int, default=120,
                        help="frame to read back when --framebuffer is set")
    parser.add_argument("--framebuffer-frames", default="",
                        help="comma-separated readback frames; implies --framebuffer")
    args = parser.parse_args()
    if args.freecam_toggle and not args.play:
        raise RuntimeError("--freecam-toggle requires --play")
    if args.play:
        args.variant = "play"
        args.objects = True
        args.frames = 0
    if args.combat_smoke:
        args.variant = "play"
        args.objects = True
        args.frames = 300
    if args.actor_ray_smoke:
        args.variant = "play"
        args.objects = True
        args.frames = 300
        # The player wrapper starts at the retail map spawn, not the viewer
        # camera. Place chiefcam's test biped relative to that same start.
        args.camera = [98.49, -157.64, 3.10, 76.1, 0.0]
    if args.actor_pistol_smoke:
        args.variant = "play"
        args.objects = True
        args.frames = 300
        args.camera = [98.49, -157.64, 3.10, 76.1, 0.0]
    if args.actor_ar_smoke:
        args.variant = "play"
        args.objects = True
        args.frames = 300
        args.camera = [98.49, -157.64, 3.10, 76.1, 0.0]
    if args.shotgun_reload_smoke:
        args.variant = "play"
        args.objects = True
        args.frames = 900
    if args.grenade_smoke:
        if args.freecam or args.freecam_toggle:
            raise RuntimeError("--grenade-smoke must run with player collision; freecam options are not allowed")
        args.variant = "play"
        args.objects = True
        args.frames = 300
    if args.fuel_still:
        args.variant = "play"
        args.objects = True
        args.frames = 90
        args.framebuffer_frames = "70"
    if args.variant == "stream":
        args.frames = max(args.frames, 360)
    if args.framebuffer_frames:
        args.framebuffer = True
        args.framebuffer_frame_list = [int(item) for item in args.framebuffer_frames.split(",") if item]
    else:
        args.framebuffer_frame_list = [args.framebuffer_frame] if args.framebuffer else []
    if (args.cache_pages or args.cache_route) and args.variant != "stream":
        raise RuntimeError("Cache stress options require --variant stream")
    if args.cache_pages < 0 or any(not 1 <= frame <= args.frames for frame in args.framebuffer_frame_list):
        raise RuntimeError("Invalid cache page limit or framebuffer frame")
    if not args.play and not 60 <= args.frames <= 18000:
        raise RuntimeError("Choose 60 through 18000 frames")
    if args.route:
        args.frames = 9000
        args.objects = True
    if args.freecam:
        args.frames = 3000
        args.objects = True
    require_platform()
    build_name = "world-stream-elf" if args.variant == "stream" else "world-portal-elf" if args.variant == "portal" else "world-play-elf" if args.variant == "play" else "world-elf"
    report = json.loads((ROOT / "build" / build_name / "result.json").read_text())
    original = ROOT / "build" / build_name / "world.elf"
    if sha(original) != report["elf_sha256"]:
        raise RuntimeError("World ELF changed after build")
    for name, digest in report["source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rebuild the viewer after changing " + name)
    converted = json.loads((ROOT / "build/convert/bloodgulch.json").read_text())
    packs = (ROOT / converted.get("pack_directory", "data/retail/convert/bloodgulch/run-a")).resolve()
    if not packs.is_relative_to(ROOT / "data/retail"):
        raise RuntimeError("Converted packs must remain under private data/retail")
    suffixes = {"bsp": ".hp2", "textures": ".tex.hp2", "objects": ".obj.hp2"}
    for kind, suffix in suffixes.items():
        if sha(packs / ("bloodgulch" + suffix)) != converted["pack_sha256"][kind]:
            raise RuntimeError("Converted pack hash differs: " + kind)
    stop_previous()
    play_boot = args.play or args.fuel_still or args.combat_smoke or args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke or args.shotgun_reload_smoke or args.grenade_smoke
    label = "world-stream" if args.variant == "stream" else "world-portal" if args.variant == "portal" else "world"
    run = OUTPUT / "runs" / f"{label}-{args.mode}-{uuid.uuid4().hex}"
    boot = run / "boot"
    boot.mkdir(parents=True)
    if args.variant == "stream":
        (boot / "stream-fixture.bin").write_bytes(bytes(i ^ 0xa5 for i in range(256)))
    elf = boot / "world.elf"
    shutil.copy2(original, elf)
    for suffix in suffixes.values():
        (boot / ("bloodgulch" + suffix)).symlink_to(packs / ("bloodgulch" + suffix))
    if play_boot:
        play_objects = ROOT / "build/play-objects"
        if not (play_objects / "bloodgulch.obj.hp2").is_file() or not (play_objects / "weapons.fp").is_file():
            subprocess.run([sys.executable, str(ROOT / "tools/play_weapons.py")], check=True)
        objects = boot / "bloodgulch.obj.hp2"
        objects.unlink()
        objects.symlink_to(play_objects / "bloodgulch.obj.hp2")
        shutil.copy2(play_objects / "weapons.fp", boot / "weapons.fp")
    if args.fuel_still:
        (boot / "fpstill.txt").write_text("weapons\\fuel rod gun\\fuel rod\n")
    if args.actor_ray_smoke:
        (boot / "fpstill.txt").write_text("weapons\\shotgun\\shotgun\n")
    if args.actor_pistol_smoke:
        (boot / "fpstill.txt").write_text("weapons\\pistol\\pistol\n")
    if args.actor_ar_smoke:
        (boot / "fpstill.txt").write_text("weapons\\assault rifle\\assault rifle\n")
    if args.shotgun_reload_smoke:
        (boot / "fpstill.txt").write_text("weapons\\shotgun\\shotgun\n")
    if args.play or args.fuel_still or args.combat_smoke or args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke or args.shotgun_reload_smoke or args.grenade_smoke:
        sys.path.insert(0, str(ROOT / "tools"))
        from convert_collision import build_pack
        decompressed = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"
        if not decompressed.is_file():
            raise RuntimeError("Decompressed Blood Gulch is required for the collision walk")
        (boot / "collision.hp2").write_bytes(build_pack(decompressed))
    overlay = "0" if play_boot or args.motion else "1"
    fp = "1" if play_boot else "0"
    lines = ["pack bloodgulch.hp2", "tex bloodgulch.tex.hp2", "arena_mb 12", "textures 1", "lightmaps 1", "clipbudget 1000",
             "camera " + " ".join(map(str,args.camera)), "frames " + str(args.frames), "fps 30", "hold 1",
             "overlay " + overlay, "printcam 1", "fp " + fp, "lodctl 0"]
    if args.force_conservative:
        lines += ["debug 64"]
    if args.framebuffer:
        lines = [line for line in lines if not line.startswith("overlay ")] + ["overlay 0"]
        lines += ["fbdump " + str(frame) for frame in args.framebuffer_frame_list]
    if args.cache_pages:
        lines.append("cache_pages " + str(args.cache_pages))
    if args.cache_route:
        lines.append("cache_route 1")
    if args.objects:
        lines += ["obj bloodgulch.obj.hp2", "objects 1", "sky3d 1", "skyfog 1", "objanim 0"]
    if args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke:
        # The engine spawns the scenario's declared player biped three units
        # ahead of the start camera. This smoke must hit that live object.
        lines.append("chiefcam 1")
    if args.motion:
        keys = [line.strip() for line in args.motion.read_text().splitlines() if line.strip()]
        if not keys or len(keys) > 24:
            raise RuntimeError("Motion path needs 1 to 24 keys")
        lines += ["pathkey " + key for key in keys]
    if args.route:
        lines += ["pathkey " + " ".join(map(str, key)) for key in ROUTE]
    cfg = boot / "halo.cfg"
    cfg.write_text("\n".join(lines) + "\n")
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    display = os.environ.get("DISPLAY") or config["display"]
    visible_display = display == config["display"]
    ini = prepare(config, run, args.mode)
    if args.play or args.combat_smoke or args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke or args.shotgun_reload_smoke or args.grenade_smoke:
        pad = configparser.ConfigParser(interpolation=None)
        pad.optionxform = str
        pad.read(ini)
        pad["Pad1"].update(RUp="Keyboard/Up", RDown="Keyboard/Down", RLeft="Keyboard/Right",
                           RRight="Keyboard/Left", Cross="Keyboard/G", Circle="Keyboard/Control",
                           R1="Keyboard/F", R3="Keyboard/4", Square="Keyboard/R", Triangle="Keyboard/Q")
        with ini.open("w") as handle:
            pad.write(handle)
    log = run / "emulog.txt"
    command = [config["binary"], "-datapath", str(run / "data"), "-nofullscreen", "-logfile", str(log), "-elf", str(elf)]
    result = {"status":"running", "scenario":"bloodgulch-static", "mode":args.mode, "visible":visible_display, "command":command,
              "runner_sha256":sha(Path(__file__)), "elf_sha256":sha(elf), "source_sha256":report["source_sha256"], "pack_sha256":converted["pack_sha256"],
              "settings_sha256":sha(ini), "config_sha256":sha(cfg), "camera":args.camera, "requested_frames":args.frames,
              "bios_sha256":sha(config["bios"]), "emulator_sha256":sha(Path(config["binary"]).resolve()),
              "run_directory":str(run), "log":str(log), "captures":[], "cache_pages":args.cache_pages,
              "cache_route":args.cache_route,
              "framebuffer_frame":args.framebuffer_frame_list[0] if args.framebuffer_frame_list else None,
              "framebuffer_frames":args.framebuffer_frame_list if args.framebuffer else None,
              "limits":"Diagnostic static viewer; no M10 completion or hardware performance claim."}
    if args.variant == "stream":
        result["stream_fixture_sha256"] = sha(boot / "stream-fixture.bin")
    result["variant"] = args.variant
    result["visibility"] = "conservative" if args.force_conservative or args.variant == "conservative" else "portal"
    path = run / "result.json"
    save(path,result)
    # Validate that input/capture can reach the visible desktop before starting
    # PCSX2; otherwise a display-access failure leaves an orphaned emulator.
    keyboard = Input() if args.freecam or args.combat_smoke or args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke or args.shotgun_reload_smoke or args.grenade_smoke or args.freecam_toggle else None
    try:
        process = subprocess.Popen(command,cwd=boot,env={**os.environ,"DISPLAY":display,"QT_QPA_PLATFORM":"xcb","APPIMAGE_EXTRACT_AND_RUN":"1"},stdout=(run/"launcher.log").open("w"),stderr=subprocess.STDOUT,start_new_session=True)
    except Exception:
        if keyboard: keyboard.close()
        raise
    save(OUTPUT / "active.json",{"pid":process.pid,"run_directory":str(run)})
    print("Visible Blood Gulch viewer; evidence: " + str(run),flush=True)
    start = progress = time.monotonic(); size = 0; window = None
    held = ()
    fire_held = False
    fire_started = False
    fire_next_at = 0.0
    fire_release_at = 0.0
    fire_released = False
    actor_ar_start_tick = None
    shotgun_focus_refresh = 0.0
    grenade_started = False
    grenade_aim_started = False
    grenade_aim_release_at = 0.0
    grenade_release_at = 0.0
    grenade_released = False
    freecam_toggle_sent = False
    try:
        while time.monotonic()-start < 7200:
            text = log.read_text(errors="replace") if log.exists() else ""
            if len(text)!=size: size=len(text); progress=time.monotonic()
            if "[err]" in text or " OVERFLOW" in text:
                raise RuntimeError("Viewer reported an error or DMA overflow")
            if window is None:
                owned=windows(process.pid)
                if owned:
                    window=owned[0][0]
                    if visible_display:
                        subprocess.run(["wmctrl","-ir",window,"-e","0,80,80,1024,768"],check=True);focus(window)
            if args.freecam and window:
                samples = re.findall(r"\[cam\] pos (-?\d+\.\d+) (-?\d+\.\d+) (-?\d+\.\d+) yaw (-?\d+\.\d+)", text)
                # Use the actual pad camera, with no pathkeys. Slow input and
                # logged-position feedback avoid flying past the whole map in
                # one two-second camera-report interval.
                targets = ((20, -170, 9), (120, -170, 9), (120, -60, 9),
                           (20, -60, 9), (65, -95, 24))
                waypoint = getattr(keyboard, "waypoint", 0)
                keys = ()
                if samples:
                    x, y, z, yaw = map(float, samples[-1])
                    if waypoint < len(targets):
                        tx, ty, tz = targets[waypoint]
                        dx, dy, dz = tx-x, ty-y, tz-z
                        if math.hypot(dx, dy) < 18 and abs(dz) < 8:
                            waypoint += 1
                            print("Pad camera waypoint " + str(waypoint) + ": " + str((x,y,z)), flush=True)
                            result.setdefault("pad_waypoints", []).append([x,y,z])
                            save(path, result)
                        else:
                            yaw = math.radians(yaw)
                            forward = dx*math.cos(yaw) + dy*math.sin(yaw)
                            strafe = dx*math.sin(yaw) - dy*math.cos(yaw)
                            keys = tuple((["W" if forward > 0 else "S"] if abs(forward) > 10 else []) +
                                         (["D" if strafe > 0 else "A"] if abs(strafe) > 10 else []) +
                                         (["E" if dz > 0 else "Q"] if abs(dz) > 8 else []))
                keyboard.waypoint = waypoint
                now = time.monotonic()
                if keys != held or (keys and now - getattr(keyboard, "sent", 0) > 2):
                    focus(window)
                    for key in held:
                        keyboard.key(key, False)
                    # Releasing before re-pressing also repairs focus-loss input.
                    for key in keys:
                        keyboard.key(key, True)
                    held = keys
                    keyboard.sent = now
            if args.play and window and "[play] ready" in text:
                if args.freecam_toggle and not freecam_toggle_sent:
                    focus(window)
                    keyboard.key("4", True)
                    time.sleep(.12)
                    keyboard.key("4", False)
                    freecam_toggle_sent = True
                    result["freecam_toggle"] = "enabled via R3; press 4 again to return to collision player"
                    save(path, result)
                    print("In-game freecam toggled on with R3/4; press 4 again to return to colliding player control.", flush=True)
                    time.sleep(.2)
                result.update(status="playing", wall_seconds=time.monotonic()-start)
                save(path, result)
                print("Collision walk is live. The window stays open.", flush=True)
                print("W S walk, A D strafe, arrows look, G jump, Control crouch, 4 toggles freecam.", flush=True)
                return
            actor_ar_ticks = [int(match) for match in re.findall(
                r"\[play\] fire ASSAULT RIFLE (?:trigger \d+|\d+) pellets \d+ tick (\d+)", text)]
            if args.actor_ar_smoke and actor_ar_ticks and actor_ar_start_tick is None:
                actor_ar_start_tick = actor_ar_ticks[0]
            if (args.combat_smoke or args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke or args.shotgun_reload_smoke) and window and "[play] ready" in text and not fire_started:
                focus(window)
                keyboard.key("f", False)
                time.sleep(.1)
                keyboard.key("f", True)
                fire_held = True
                fire_started = True
                fire_next_at = time.monotonic() + (1.4 if args.combat_smoke or args.actor_pistol_smoke else 1.0e9)
                fire_release_at = time.monotonic() + (3600.0 if args.actor_ar_smoke or args.shotgun_reload_smoke else .15)
                print("Combat smoke: pulsing pistol fire on the fixed probe target." if args.combat_smoke
                      else "Actor-pistol smoke: pulsing pistol fire into the live scenario biped." if args.actor_pistol_smoke
                      else "Actor assault-rifle smoke: sustaining fire against the live biped." if args.actor_ar_smoke
                      else "Shotgun reload smoke: emptying all 12 shells before release.", flush=True)
            shotgun_fire = re.findall(r"\[play\] fire SHOTGUN (\d+) pellets (\d+) tick (\d+) loaded (\d+)", text)
            shotgun_empty = (args.shotgun_reload_smoke and len(shotgun_fire) >= 12 and
                             int(shotgun_fire[11][3]) == 0)
            if shotgun_empty and fire_held and not fire_released and window:
                focus(window)
                keyboard.key("f", False)
                fire_held = False
                fire_released = True
                print("Shotgun reload smoke: empty magazine observed; released primary for shell reload.", flush=True)
            if args.shotgun_reload_smoke and fire_held and window and time.monotonic() >= shotgun_focus_refresh:
                focus(window)
                shotgun_focus_refresh = time.monotonic() + 1.0
            actor_ar_release_due = (args.actor_ar_smoke and actor_ar_start_tick is not None and
                actor_ar_ticks and actor_ar_ticks[-1] - actor_ar_start_tick >= 96)
            if (args.combat_smoke or args.actor_ray_smoke or args.actor_pistol_smoke or args.actor_ar_smoke or args.shotgun_reload_smoke) and fire_held and not fire_released and (
                    actor_ar_release_due if args.actor_ar_smoke else time.monotonic() >= fire_release_at):
                focus(window)
                keyboard.key("f", False)
                fire_held = False
                if args.actor_ar_smoke:
                    fire_released = True
                    print("Actor assault-rifle smoke: released after 96 simulation ticks.", flush=True)
            actor_target_dead = args.actor_pistol_smoke and bool(re.search(
                r"\[play\] actor damage .* dead 1", text))
            if (args.actor_pistol_smoke and actor_target_dead and not fire_released and window):
                focus(window)
                keyboard.key("f", False)
                fire_held = False
                fire_released = True
                print("Actor pistol smoke: live-biped death observed; released fire.", flush=True)
            if ((args.combat_smoke or args.actor_pistol_smoke) and fire_started and not fire_held and not fire_released and
                    time.monotonic() >= fire_next_at):
                focus(window)
                keyboard.key("f", True)
                fire_held = True
                fire_next_at = time.monotonic() + 1.4
                fire_release_at = time.monotonic() + .15
            if args.combat_smoke and fire_held and not fire_released:
                if re.search(r"\[play\] probe damage .* dead 1", text):
                    focus(window)
                    keyboard.key("f", False)
                    fire_held = False
                    fire_released = True
                    print("Combat smoke: probe target death observed; released fire.", flush=True)
            if (args.grenade_smoke and window and "[play] ready" in text and
                    not grenade_aim_started):
                focus(window)
                keyboard.key("Down", True)
                grenade_aim_started = True
                grenade_aim_release_at = time.monotonic() + .65
                print("Grenade smoke: pitching the collision player down before the throw.", flush=True)
            if (args.grenade_smoke and grenade_aim_started and not grenade_started and
                    time.monotonic() >= grenade_aim_release_at):
                focus(window)
                keyboard.key("Down", False)
                keyboard.key("1", True)
                grenade_started = True
                grenade_release_at = time.monotonic() + .15
                print("Grenade smoke: pressed L2 once to throw a frag grenade from the player.", flush=True)
            if (args.grenade_smoke and grenade_started and not grenade_released and
                    time.monotonic() >= grenade_release_at):
                focus(window)
                keyboard.key("1", False)
                grenade_released = True
            if play_boot and "[play] collision pack" in text:
                raise RuntimeError("Collision walk did not load")
            if window and "[prof] frames=" in text and not result["captures"]:
                capture(window,run/"visible-start.png");result["captures"].append(str(run/"visible-start.png"));save(path,result)
            if window and args.motion:
                for mark in re.findall(r"\[prof\] frames=(\d+) ", text):
                    shot = run / ("gameplay-" + mark + ".png")
                    if str(shot) in result["captures"]:
                        continue
                    capture(window, shot)
                    result["captures"].append(str(shot))
                    save(path, result)
            if window and args.route:
                samples = re.findall(r"\[prof\] frames=(\d+) ", text)
                frame = int(samples[-1]) if samples else 0
                bucket = frame // 750
                if bucket > 0 and bucket != result.get("route_capture_bucket"):
                    shot = run / ("visible-route-%02d.png" % bucket)
                    capture(window,shot)
                    result["captures"].append(str(shot))
                    result["route_capture_bucket"] = bucket
                    save(path,result)
            done=re.search(r"\[done\] frames=(\d+) dropped=(\d+)",text)
            if window and done:
                if int(done[1])<args.frames or "[cfg] no host:halo.cfg" in text:
                    raise RuntimeError("Viewer did not execute the requested local scenario")
                if args.variant == "stream":
                    cycles = re.findall(r"\[stream\] cycle=(\d+) cancel/reload/contents/drain=ok", text)
                    measured = re.search(r"\[stream\] passed cycles=3 short-read=discarded high=(\d+) reserved=(\d+)", text)
                    unloads = re.findall(r"\[stream\] unload_reload=(\d+) used=(\d+) baseline=(\d+) cache_pages=(\d+)", text)
                    if cycles != ["0", "1", "2"] or not measured:
                        raise RuntimeError("Streaming request lifecycle diagnostic did not pass")
                    if [u[0] for u in unloads] != ["1", "2", "3"] or any(u[1] != u[2] for u in unloads) or "[stream] map_unload_reload=passed cycles=3" not in text:
                        raise RuntimeError("World unload/reload did not return arena use to baseline")
                    if int(measured[1]) != 1048576 or int(measured[2]) > 1572864:
                        raise RuntimeError("Streaming diagnostic exceeded its reservation")
                    if "[stream] dma_page=ok " not in text:
                        raise RuntimeError("Texture page was not held until DMA completion")
                    if "[stream] cache_miss_source=staging " not in text or "[stream] cache_miss_sweep=ok " not in text or "[stream] cache_miss_dma=ok " not in text:
                        raise RuntimeError("Cache miss was not leased for the whole sweep")
                    result["streaming"] = {"cycles": 3, "map_reload_cycles": 3, "high_water": int(measured[1]), "arena_used": [int(u[1]) for u in unloads],
                                           "reserved": int(measured[2]), "scope": "synthetic worker reads; no texture or whole-map unload claim"}
                    if args.cache_pages:
                        churn = re.search(r"\[stream\] texture_churn evictions=(\d+) failed=(\d+) deferred=(\d+) pages=(\d+)", text)
                        if not churn or int(churn.group(1)) < 1:
                            raise RuntimeError("Forced cache limit did not cause a rendered texture eviction")
                        result["streaming"]["texture_churn"] = {
                            "evictions": int(churn.group(1)), "failed": int(churn.group(2)),
                            "deferred": int(churn.group(3)), "pages": int(churn.group(4))}
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
                    if len(result.get("pad_waypoints", [])) != 5:
                        raise RuntimeError("Pad-camera waypoint flight did not finish")
                    result["camera_span"] = span
                if args.combat_smoke:
                    damage_events = re.findall(r"\[play\] probe damage ([0-9.]+) node (-?\d+) part (-?\d+) resistance (-?\d+) shield ([0-9.]+) body (-?[0-9.]+) dead (\d+)", text)
                    deaths = [event for event in damage_events if event[6] == "1"]
                    fires = re.findall(r"\[play\] fire PISTOL (\d+) pellets (\d+)", text)
                    hits = re.findall(r"\[play\] hit 1 ", text)
                    shot_cost = re.findall(r"\[play\] shot-cost samples (\d+) avg-ms ([0-9.]+) max-shot-ms ([0-9.]+) max-tick-ms ([0-9.]+) max-calls-per-tick (\d+)", text)
                    if (not fire_released or not deaths or len(fires) != 6 or
                            len(damage_events) != 6 or len(hits) != 6):
                        raise RuntimeError("Integrated play combat did not fire, hit, and kill the probe target")
                    result["combat_smoke"] = {
                        "weapon": "PISTOL", "fire_events": len(fires), "probe_damage_events": len(damage_events),
                        "final_damage": float(deaths[-1][0]), "final_shield": float(deaths[-1][4]),
                        "final_body": float(deaths[-1][5]), "target_dead": True,
                        "hit_node": int(damage_events[-1][1]), "hit_damage_part": int(damage_events[-1][2]),
                        "hit_resistance_index": int(damage_events[-1][3]),
                        "shot_tick_cost_windows": [
                            {"samples": int(row[0]), "avg_ms": float(row[1]),
                             "max_shot_ms": float(row[2]), "max_tick_ms": float(row[3]),
                             "max_calls_per_tick": int(row[4])}
                            for row in shot_cost],
                        "target": "retail cyborg collision mesh in a fixed bind-pose probe placement; not a live actor"}
                if args.actor_ray_smoke:
                    fires = re.findall(r"\[play\] fire SHOTGUN (?:trigger \d+|\d+) pellets (\d+)", text)
                    live_actors = re.findall(r"\[play\] live-actor object (\d+) def (\d+) model-tag ([0-9a-fA-F]+) nodes (\d+)", text)
                    actor_damage = re.findall(r"\[play\] actor damage object (\d+) def (\d+) amount ([0-9.]+) node (-?\d+) region (-?\d+) part (-?\d+) resistance (-?\d+) shield ([0-9.]+) body (-?[0-9.]+) dead (\d+)", text)
                    pellet_rows = re.findall(r"\[play\] pellet-result tick (\d+) calls (\d+) actor-hits (\d+) bsp-hits (\d+) resolved (\d+) flying (\d+)", text)
                    volley = next((row for row in pellet_rows if int(row[1]) == 15), None)
                    windows_cost = re.findall(r"\[play\] shot-cost samples (\d+) avg-ms ([0-9.]+) max-shot-ms ([0-9.]+) max-tick-ms ([0-9.]+) max-calls-per-tick (\d+)", text)
                    if (not fires or int(fires[0]) != 15 or not live_actors or not actor_damage or
                            not windows_cost or max(int(row[4]) for row in windows_cost) < 15 or
                            not volley or int(volley[2]) != len(actor_damage) or
                            int(volley[2]) + int(volley[3]) != 15 or
                            int(volley[4]) != 15 or int(volley[5]) != 0):
                        raise RuntimeError("Shotgun actor-ray smoke did not account for all 15 pellets as actor damage or BSP collision in one simulation tick")
                    if int(done[2]) != 0:
                        raise RuntimeError("Shotgun actor-ray smoke dropped emulator frames")
                    result["actor_ray_smoke"] = {
                        "weapon": "SHOTGUN", "pellets": int(fires[0]),
                        "live_actor": {"object_index": int(live_actors[0][0]), "definition_index": int(live_actors[0][1]),
                                       "model_tag": int(live_actors[0][2], 16), "node_count": int(live_actors[0][3])},
                        "actor_damage_events": len(actor_damage),
                        "pellet_outcomes": {"tick": int(volley[0]), "calls": int(volley[1]),
                                            "actor_damage_hits": int(volley[2]), "bsp_surface_hits": int(volley[3]),
                                            "resolved": int(volley[4]), "still_flying": int(volley[5])},
                        "last_actor_hit": {"node": int(actor_damage[-1][3]), "region": int(actor_damage[-1][4]),
                                           "damage_part": int(actor_damage[-1][5]),
                                           "resistance_index": int(actor_damage[-1][6]), "dead": actor_damage[-1][9] == "1"},
                        "shot_tick_cost_windows": [
                            {"samples": int(row[0]), "avg_ms": float(row[1]),
                             "max_shot_ms": float(row[2]), "max_tick_ms": float(row[3]),
                             "max_calls_per_tick": int(row[4])}
                            for row in windows_cost],
                        "target": "scenario player biped at live animated pose; target-specific vitality; emulator counter is not physical PS2 timing"}
                if args.actor_pistol_smoke:
                    fires = re.findall(r"\[play\] fire PISTOL (?:trigger \d+|\d+) pellets (\d+)", text)
                    live_actors = re.findall(r"\[play\] live-actor object (\d+) def (\d+) model-tag ([0-9a-fA-F]+) nodes (\d+)", text)
                    actor_damage = re.findall(r"\[play\] actor damage object (\d+) def (\d+) amount ([0-9.]+) node (-?\d+) region (-?\d+) part (-?\d+) resistance (-?\d+) shield ([0-9.]+) body (-?[0-9.]+) dead (\d+)", text)
                    deaths = [event for event in actor_damage if event[9] == "1"]
                    if (not fire_released or not fires or not live_actors or not actor_damage or
                            not deaths or any(int(row[0]) != 1 for row in fires) or int(done[2]) != 0):
                        raise RuntimeError("Pistol actor smoke did not kill the live scenario biped with single-projectile hits and no dropped frames")
                    result["actor_pistol_smoke"] = {
                        "weapon": "PISTOL", "fire_events": len(fires),
                        "actor_damage_events": len(actor_damage), "target_dead": True,
                        "live_actor": {"object_index": int(live_actors[0][0]), "definition_index": int(live_actors[0][1]),
                                       "model_tag": int(live_actors[0][2], 16), "node_count": int(live_actors[0][3])},
                        "last_actor_hit": {"node": int(deaths[-1][3]), "region": int(deaths[-1][4]),
                                           "damage_part": int(deaths[-1][5]), "resistance_index": int(deaths[-1][6]),
                                           "shield": float(deaths[-1][7]), "body": float(deaths[-1][8])},
                        "target": "scenario player biped with ACOL pose and cyborg-tagged vitality"}
                if args.actor_ar_smoke:
                    fire_lines = re.findall(r"\[play\] fire ASSAULT RIFLE (?:trigger \d+|\d+) pellets (\d+) tick (\d+)(?: magazine \d+ loaded (\d+)| loaded (\d+))", text)
                    live_actors = re.findall(r"\[play\] live-actor object (\d+) def (\d+) model-tag ([0-9a-fA-F]+) nodes (\d+)", text)
                    actor_damage = re.findall(r"\[play\] actor damage object (\d+) def (\d+) amount ([0-9.]+) node (-?\d+) region (-?\d+) part (-?\d+) resistance (-?\d+) shield ([0-9.]+) body (-?[0-9.]+) dead (\d+)", text)
                    deaths = [event for event in actor_damage if event[9] == "1"]
                    ticks = [int(row[1]) for row in fire_lines]
                    loaded = [int(row[2] or row[3]) for row in fire_lines]
                    if (not fire_released or len(fire_lines) < 45 or not live_actors or not deaths or
                            int(done[2]) != 0 or any(int(row[0]) != 1 for row in fire_lines) or
                            ticks[-1] - ticks[0] < 90 or
                            any(b - a != 2 for a, b in zip(ticks, ticks[1:])) or
                            any(b != a - 1 for a, b in zip(loaded, loaded[1:]))):
                        raise RuntimeError("Assault-rifle actor smoke failed sustained 15-round/s cadence, one-round ammo consumption, target damage/death, or frame validation")
                    result["actor_ar_smoke"] = {
                        "weapon": "ASSAULT RIFLE", "sustain_simulation_ticks": ticks[-1] - ticks[0],
                        "projectiles": len(fire_lines), "simulation_ticks": ticks,
                        "magazine_loaded_after_each_shot": loaded,
                        "target_dead": True,
                        "live_actor": {"object_index": int(live_actors[0][0]), "definition_index": int(live_actors[0][1]),
                                       "model_tag": int(live_actors[0][2], 16), "node_count": int(live_actors[0][3])},
                        "last_actor_hit": {"node": int(deaths[-1][3]), "region": int(deaths[-1][4]),
                                           "damage_part": int(deaths[-1][5]), "resistance_index": int(deaths[-1][6]),
                                           "shield": float(deaths[-1][7]), "body": float(deaths[-1][8])},
                        "target": "scenario player biped with ACOL pose and cyborg-tagged vitality"}
                if args.shotgun_reload_smoke:
                    fire_rows = re.findall(
                        r"\[play\] fire SHOTGUN (\d+) pellets (\d+) tick (\d+) loaded (\d+)", text)
                    state_rows = [tuple(map(int, row)) for row in re.findall(
                        r"\[play\] shotgun-state tick (\d+) loaded (-?\d+) total (-?\d+) magazine (-?\d+) timer (-?\d+)", text)]
                    shell_rows = []
                    max_loaded = 0
                    for row in state_rows:
                        if row[1] == max_loaded + 1 and row[1] + row[2] == 12:
                            shell_rows.append(row)
                            max_loaded = row[1]
                    shell_ticks = [row[0] for row in shell_rows]
                    shell_loaded = [row[1] for row in shell_rows]
                    if (not fire_released or len(fire_rows) != 12 or
                            [int(row[3]) for row in fire_rows] != list(range(11, -1, -1)) or
                            not state_rows or state_rows[0][1:3] != (12, 12) or
                            len(shell_rows) != 12 or shell_loaded != list(range(1, 13)) or
                            shell_rows[-1][2] != 0 or
                            any(b - a != shell_ticks[1] - shell_ticks[0]
                                for a, b in zip(shell_ticks[1:], shell_ticks[2:])) or
                            int(done[2]) != 0):
                        raise RuntimeError("Shotgun reload smoke failed to empty 12 shells and load 12 reserve shells at a stable integrated interval")
                    result["shotgun_reload_smoke"] = {
                        "shots": len(fire_rows), "post_shot_loaded": [int(row[3]) for row in fire_rows],
                        "reload_shells": len(shell_rows), "loaded_after_each_shell": shell_loaded,
                        "total_after_last_shell": shell_rows[-1][2], "shell_load_ticks": shell_ticks,
                        "shell_interval_ticks": shell_ticks[1] - shell_ticks[0],
                        "source_profile": "retail Blood Gulch shotgun tag: 12-round magazine, one shell per reload step",
                        "reference": "Halo CE Universal weapon magazine reload completion/chaining; PS2 gun state machine uses fixed-size state and no heap"}
                if args.grenade_smoke:
                    throws = re.findall(r"\[play\] grenade throw frag carried (\d+) slot (\d+) mode player eye (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+) aim (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+)", text)
                    explosions = re.findall(r"\[play\] grenade explosion frag slot (\d+) target (actor|probe)(?: damage ([0-9.]+) distance ([0-9.]+) shield ([0-9.]+) body (-?[0-9.]+) dead (\d+)| outside ([0-9.]+))", text)
                    if (not grenade_released or len(throws) != 1 or not explosions or
                            float(throws[0][7]) >= 0.0 or
                            any(row[1] != "actor" for row in explosions)):
                        raise RuntimeError("EE grenade smoke did not throw from the collision player and detonate against the live scenario biped")
                    result["grenade_smoke"] = {
                        "throws": len(throws), "carried_after_throw": int(throws[0][0]),
                        "slot": int(throws[0][1]), "throw_origin_eye": [float(v) for v in throws[0][2:5]],
                        "throw_aim": [float(v) for v in throws[0][5:8]],
                        "control": "collision-resolved player (mover_tick_map); freecam disabled",
                        "explosions": len(explosions),
                        "target": "live scenario biped collision/vitality state"}
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
        if keyboard and fire_held and not fire_released:
            keyboard.key("f", False)
        if keyboard and grenade_started and not grenade_released:
            keyboard.key("1", False)
        if keyboard and held:
            for key in held: keyboard.key(key, False)
        if keyboard: keyboard.close()


if __name__ == "__main__":
    try: main()
    except (OSError,RuntimeError,subprocess.SubprocessError) as error: sys.exit(f"World viewer failed: {error}")
