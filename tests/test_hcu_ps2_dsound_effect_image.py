"""Keep the Xbox DSP firmware image out of PS2 builds only."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submodules/halo-ce-universal/source/sound/sound_dsound_xbox.c"


def _guarded_region(source: str, token: str) -> str:
    """Return the preprocessor block containing token, respecting nesting."""
    position = source.index(token)
    lines = source[:position].splitlines(keepends=True)
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append((cursor, line))
        cursor += len(line)

    opener = None
    depth = 0
    for offset, line in reversed(offsets):
        stripped = line.lstrip()
        if stripped.startswith("#endif"):
            depth += 1
        elif stripped.startswith(("#if ", "#ifdef ", "#ifndef ")):
            if depth == 0:
                opener = (offset, line)
                break
            depth -= 1
    assert opener is not None, f"{token!r} has no enclosing preprocessor guard"
    guard_start, guard_line = opener
    assert "!defined(HALO_PS2)" in guard_line

    depth = 0
    for index in range(guard_start, len(source)):
        if source.startswith("#if ", index) or source.startswith("#ifdef ", index) or source.startswith("#ifndef ", index):
            depth += 1
        elif source.startswith("#endif", index):
            depth -= 1
            if depth == 0:
                return source[guard_start:index]
    raise AssertionError(f"unterminated guard for {token!r}")


def test_xbox_dsp_image_and_download_are_excluded_only_for_ps2():
    source = SOURCE.read_text(encoding="utf-8")
    image = _guarded_region(source, "static byte const dsound_effects_image[0x3A5C]")
    download = _guarded_region(source, "IDirectSound_DownloadEffectsImage(")

    assert "dsound_effects_image" in image
    assert "dsound_effects_image" in download
    assert "IDirectSound_DownloadEffectsImage" in download
    assert "port: the Xbox DSP effects firmware is not used by the PS2 sound path." in image
    assert "port: this Xbox-only DSP image is absent from the PS2 build." in download


def test_ps2_sound_manager_declines_the_unimplemented_platform_backend():
    preferences = (ROOT / "submodules/halo-ce-universal/source/sound/sound_preferences.c").read_text()
    manager = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()

    assert "#ifdef HALO_PS2\n\t-1,\n#else\n\t0,\n#endif" in preferences
    init = manager[manager.index("void sound_initialize("):]
    platform_check = init.index("if (platform_code < 0 || platform_code >= 2)")
    platform_initialize = init.index("platform_definition->initialize(preferences)")
    assert platform_check < platform_initialize
    direct_sound_create = edge[edge.index("long __stdcall DirectSoundCreate("):]
    assert "*device = 0;" in direct_sound_create
    assert "return (long)0x80004005;" in direct_sound_create
