# M2 C2 r5 partition-runtime evidence (2026-10-23)

Lane: partition-runtime (C2.2 bounded partition, C2.4 production registration).
Build directory: `build/m2-c2-r5-partition-runtime/`.

## Changed files

- `src/stream/hcu_memory_profile.h`: `residency_bytes` is the last field of `hcu_memory_profile_t`, so existing positional initializers keep working with zero. The partition gains `residency_base`, `residency_bytes` and `residency_guard_bytes`.
- `src/stream/hcu_memory_profile.c`: plan validates whole 64 KiB slots and the fit. Bind allocates the render span, a 16-byte guard, then the residency span from the texture parent. Guards are checked for the new guard and span. The 27 table rows carry `residency_bytes = 1048576` (16 slots), and each row's render residual drops by 1048592.
- `src/stream/hcu_main.c`: a static 16-entry residency table, and `hcu_register_selected_runtime()`, which runs after map-service init and before the legacy renderer gate. A bootstrap boot is unchanged. A qualified row fails closed.
- `tests/hcu_mp_partition_table_main.c`: checks the residency span and exact fill, and stubs the binder hooks for a table-only link.
- `tests/test_hcu_c2_budget_partition.py`: expects `residency_bytes` in the table and the C rows.

## Results

- `hcu_mp_partition_table_main`: `partition-table-v2 rows=27 failures=0`, exit 0.
- `hcu_mp_production_bind_capacity_main` (zero-residency profiles): exit 0, all required markers present.
- `pytest tests/test_hcu_main_wiring.py tests/test_hcu_map_service_profile.py`: 10 passed. The wiring test also compiles `hcu_main.c` for the EE.
- `pytest tests/test_hcu_c2_budget_partition.py`: 2 failed, 2 passed. Failure: `KeyError: 'residency_bytes'` at `tests/test_hcu_c2_budget_partition.py:50` and `:70`. The generator `tools/audit_hcu_c2_partition_budget.py` (budget lane, not edited) still emits the old three-field rows.
- EE objects built through `make -f tools/ee-world.mk WORLD_HCU_GAMEPLAY=1 WORLD_OUTPUT=build/m2-c2-r5-partition-runtime/ee` with `PS2SDK` and the EE toolchain bin on `PATH`: `hcu_main.o`, `hcu_map_service.o`, `hcu_memory_profile.o` built with no warnings.
- `git diff --check` clean for the touched files and both touched submodules.

## Open gaps

- Residency bind is not exercised by a host test. The bind-capacity test (not in this lane) uses zero-residency profiles only.
- The 16-slot count is the requirement's fallback, not measured. The 27-package mount test with smaller arenas was not run.
- Production registration is not reachable. The pinned HCP package digest, metadata blob, package reader, source reader, and relocation and stream scratch from named owners are not built into this image. A qualified row therefore refuses to boot with the message in `hcu_register_selected_runtime`. The package reader could be built on `hcu_file_bridge_read` and `hcu_file_bridge_seek`.
- The 16-entry residency table is ELF static storage, not CE-budgeted. The budget lane should decide whether to charge it.

## Cross-lane requests

- Budget lane: `tools/audit_hcu_c2_partition_budget.py` must emit `residency_bytes = 1048576` per row and recompute `render_texture_bytes = render - 1048592`. The generated C table must then match the hand-applied rows in `src/stream/hcu_memory_profile.c`.
- Budget lane: `config/memory-budget.json` should carry the 1 MiB residency span and the 16 KiB texture guard.
- Map service lane: no change required.

## Verdict

C2.2 partial: residency span added and table-tested, bind path not host-tested. C2.4 open: fail-closed gate only, no registration.
