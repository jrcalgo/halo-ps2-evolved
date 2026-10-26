"""Regression for emulator wrappers that exit before their detached child."""
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_guest_run  # noqa: E402


def test_cleanup_stops_detached_guest_writer_after_launcher_exits(tmp_path):
    pid_file = tmp_path / "child.pid"
    output = tmp_path / "guest-writer.log"
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "import pathlib,sys,time\n"
        "p=pathlib.Path(sys.argv[1])\n"
        "while True:\n"
        " p.open('a').write('writer\\n')\n"
        " time.sleep(0.01)\n")
    launcher_script = tmp_path / "launcher.py"
    launcher_script.write_text(
        "import pathlib,subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]],start_new_session=True)\n"
        "pathlib.Path(sys.argv[3]).write_text(str(child.pid))\n"
        "time.sleep(0.5)\n")

    launcher = subprocess.Popen(
        [sys.executable, str(launcher_script), str(child_script), str(output), str(pid_file)],
        start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    owned = c2_guest_run._refresh_owned_processes(launcher.pid, launcher.pid)
    child_pid = None
    try:
        deadline = time.monotonic() + 5
        while launcher.poll() is None and time.monotonic() < deadline:
            owned = c2_guest_run._refresh_owned_processes(launcher.pid, launcher.pid, owned)
            time.sleep(0.02)
        assert launcher.wait(timeout=1) == 0
        child_pid = int(pid_file.read_text())
        owned = c2_guest_run._refresh_owned_processes(launcher.pid, launcher.pid, owned)
        assert any(pid == child_pid for pid, _start in owned)

        status = c2_guest_run._stop_owned_process(launcher, grace=2, owned=owned)
        assert "host-exited-0" in status
        size_after_stop = output.stat().st_size
        time.sleep(0.1)
        assert output.stat().st_size == size_after_stop
        child = c2_guest_run._proc_record(child_pid)
        assert child is None or child["state"] in ("Z", "X")
    finally:
        owned = c2_guest_run._refresh_owned_processes(launcher.pid, launcher.pid, owned)
        c2_guest_run._stop_owned_process(launcher, grace=2, owned=owned)
