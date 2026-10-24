# M2 animation trace phase-tag follow-up

## Change

The trace event's former reserved 16-bit field is now a `phase` tag. A target-only compile-time size assertion in `ps2_animation_trace.h` keeps the event record at 24 bytes on R5900 and leaves the existing 4,096-event diagnostic buffer at 98,304 bytes. The new `ps2_animation_trace_phase_set()` setter returns the previous phase; CE callers save and restore it so nested scopes do not leak attribution into subsequent work.

Opt-in scopes currently tag animation reads reached from:

- `object_compute_node_matrices()` as `object_pose` ([`objects.c:2457`](../../submodules/halo-ce-universal/source/objects/objects.c#L2457)). This call tree includes `animation_get_node_orientations()` ([`objects.c:2532`](../../submodules/halo-ce-universal/source/objects/objects.c#L2532)).
- `unit_preprocess_node_orientations()` as `unit_pose` ([`units.c:11327`](../../submodules/halo-ce-universal/source/units/units.c#L11327)). This applies animation overlays and aiming-screen data.

The guards require both `HALO_PS2` and `HALO_PS2_M2_ANIMATION_TRACE`; ordinary builds have no phase setter calls. This is caller-phase attribution only. It is not a map/tag/animation identity and does not imply that an event represents decoded data or a lifetime pin.

## Verification

`python3 -m pytest -q -rs tests/test_ps2_animation_trace.py tests/test_animation_data_ranges.py tests/test_hcu_parent_link_probe.py` passed **21 tests**. The C harness verifies nested object→unit→object phase save/restore and trace validity. Source checks verify both scopes restore the caller's phase and contain their expected CE pose work. Existing trace-on/off accessor tests continue to assert identical CE pointers/return behavior.

Fresh `python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory --m2-animation-trace` result SHA-256 is `f6afcfb6a505932991a9b13447396945c36924d7e9fc875ce25a4e85c5feb265`: 341 selected sources, 370 compiled units, zero compile failures, closure gate open. The target-only size assertion compiled successfully. The rebuilt diagnostic machine ELF is `build/hcu-parent-link-probe/hcu-gameplay-machine-m2-animation-trace.elf`, SHA-256 `0d970debd367387644ef2e586d9e3126af0df9fabd71e5933ef597d080d60a52`. `readelf` reports ELF32 little-endian MIPS, R5900/MIPS3 flags, one LOAD segment, 2,094,468 LOAD file bytes (2,684 below the 2 MiB `elf_static` capacity), and 2,116,724 bytes of `.bss`; the link has zero undefined imports. The matching probe remains `acceptance=false`; the logical memory report is not proof of guest physical placement.

PCSX2 was attempted against the exact ELF with `APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py --mode both --stage m2-ui --stable-seconds 3 --timeout 120 --require-physical-placement --elf build/hcu-parent-link-probe/hcu-gameplay-machine-m2-animation-trace.elf --disc build/hcu-m1-disc-data.iso`. Interpreter exited 127 before guest startup because Qt/XCB could not access display `:0.0`; the log is `build/hcu-ps2-closure/emulator-m1-interpreter-fde78f2794fb4b7c84bf01fb4184f8a7/emulog.txt`, empty of guest output. No guest run or event trace is claimed for this phase-tagged ELF. REA `inspect_binary_layout` was unavailable because `REA_PWNTOOLS_PYTHON` is not configured; the structural observations above are from local `readelf`, not REA.

## Remaining work

Add stable map epoch, tag datum/graph index, animation ordinal, game tick, and render frame only at call sites that own those values. Expand phase coverage for first-person, vehicles/devices, camera/cinematics, and validation only after auditing every exit for restoration. Add a bounded offline trace export/decoder, then obtain representative retail campaign pose traces in a diagnostic image whose measured owner assignment preserves the 5.5 MiB reserve. The UI-only marker path is known to emit zero events and is not a workload substitute. Do not infer cache savings, simultaneous live set, or capacity from phase tags.
