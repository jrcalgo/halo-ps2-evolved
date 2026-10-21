from pathlib import Path
import subprocess
import tempfile


def test_hcu_file_bridge_handle_and_reopen_lifecycle():
    root = Path(__file__).resolve().parents[1]
    ps2sdk = root / "submodules/ps2sdk"
    engine = root / "submodules/halo-ps2/engine/src"
    with tempfile.TemporaryDirectory(prefix="hcu-file-bridge-") as temp:
        executable = Path(temp) / "hcu-file-bridge-test"
        subprocess.run([
            "cc", "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
            "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast",
            "-Wl,--wrap=malloc", "-Wl,--wrap=calloc", "-Wl,--wrap=realloc",
            "-I" + str(root / "src"), "-I" + str(engine),
            "-I" + str(ps2sdk / "common/include"),
            "-I" + str(ps2sdk / "ee/include"),
            "-I" + str(ps2sdk / "ee/rpc/filexio/include"),
            str(root / "tests/hcu_file_bridge_main.c"),
            str(root / "src/stream/hcu_file_bridge.c"),
            str(engine / "stream/file.c"),
            str(engine / "core/mem.c"), "-o", str(executable),
        ], check=True, capture_output=True, text=True)
        subprocess.run([str(executable)], check=True, capture_output=True,
                       text=True)
