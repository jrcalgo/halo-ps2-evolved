# M0 pending batch: file-backed stdio and cache-span getters

**Scope:** seven pending rooted externals: `fopen`, `fclose`, `fprintf`, and the
tag-cache/BSP-cache base and size getters. This is a source/callsite review only;
it does not approve any row or close the M0 gate.

## Evidence identity and freshness

The exact HCU closure examined here is
`build/hcu-ps2-closure/all-no-bootstrap-memory/rooted.o`, SHA-256
`f1a169d679ee354044390083945b9e74319ca0b833b01da25ff904f3ea1f5e3a`.
Its `result.json` selects `HALO_PS2_NO_BOOTSTRAP_MEMORY`, reports 369 compiled
units and 322 rooted live externals. The result JSON SHA-256 is
`229cbe4724c7f3d6c62e314ca50c92d0f2070b3804b74978fcbdc95dc958691f`.
The shared review ledger still identifies root
`0645f18c1bc7332b8f4ec161b85b947653e4673fdab1a7fa57fac4e7de64a3e1` (also 322
symbols) and has 25 pending entries, including all seven here. Their recorded
caller-section arrays match the fresh rooted object exactly, but their
caller-source hash maps do not all match current source. `source/main/main.c`
differs for all three stdio rows; `port/ps2/src/ps2_cache.c` differs for all
four getter rows. The current hashes are respectively
`8a12962678737c6590556ad5c8cf3622ea94a62c897d39d106694e131f0b9b2d` and
`0d16f16c4d5fca09871a2c1d0bdbc4b952c14f7f922f09d541bc67ba43521aef`.
These section matches establish caller identity at the object-section level,
not source-hash freshness or semantic approval.

The combined optical profile has now been rebuilt from this exact root. Its
result is `build/hcu-parent-link-probe/result-optical.json` (SHA-256
`213f7dbbcb868a334e43e218b2475c1c3256c7ee1d89e723d4741abd9953db20`), whose
`source_inputs.hcu_rooted_sha256` is exactly the root above and whose closure
report hash is `229cbe4724c7f3d6c62e314ca50c92d0f2070b3804b74978fcbdc95dc958691f`.
The combined optical gameplay ELF is `hcu-gameplay-machine-optical.elf`, SHA-256
`019dbd3a328f92756ed5a0d34011be13593ad7cf5d90c4bc5a203a65b98fadec`; its map
is SHA-256 `f8e8f522751db06e8cd8caf15a661e94c1bac9efccb7b2d65a65c5f6621cf6b1`.
The result still says `acceptance: false`, no guest execution has been observed,
and the optical callback is diagnostic/UI-only. This is a current exact-root
provider map, not a runtime or M0 sign-off.

## Findings by symbol family

| Symbol | Fresh rooted caller sections | Candidate semantics and assessment |
|---|---|---|
| `fopen` | `cheats_load`, `console_startup`, `debug_dump_memory_by_file`, `debug_dump_memory_for_file`, `director_load_camera`, `director_save_camera`, `game_state_allocation_record`, `hs_doc`, `main_frame_rate_debug`, `main_load_last_solo_map`, `objects_dump_memory`, `write_to_error_file` | A Newlib file-stream API; the closure resolves the symbol, but CE callers expect Xbox drive roots, mixed read/write modes, and actual persistent file behavior. The parent bridge is a separate fixed-slot API, not by itself evidence that `fopen` is redirected to it. |
| `fclose` | Same family except `game_state_allocation_record` | Must be paired with the actual stream provider and tested for failed-open, close, invalid/repeated close, and resource-release behavior. Merely linking Newlib does not prove the target stream's lower-level I/O mapping or descriptor stability. |
| `fprintf` | `debug_dump_memory_by_file`, `debug_dump_memory_for_file`, `director_save_camera`, `game_state_allocation_record`, `hs_doc`, `main_frame_rate_debug`, `object_dump_write`, `objects_dump_memory`, `write_to_error_file` | Formats output to `FILE*`; this is not the already separately reviewed stdout `printf` path. Some callers emit diagnostics, while others write persistent settings, docs, or save metadata. A sink/no-op would lose data and could conceal errors. |
| `physical_memory_get_structure_bsp_cache_base_address` | `cache_file_read`, `ps2_cache_mount_cbsp_for_extent`, `scenario_structure_bsp_load`, `validation_begin` | The CE-side PS2 cache adapter compares the requested read buffer to this base and materializes a decoded CBSP there. CE BSP loading and validation also rely on a stable owner. Returning a fabricated or stale pointer risks writing the wrong EE region. |
| `physical_memory_get_structure_bsp_cache_size` | Above, plus `tag_validate_claims_buffer_size` | Capacity is used to reject CBSP images that cannot fit and to compute validator scratch demand. The span must be the same bound store, with correct lifetime and alignment, as the base getter. |
| `physical_memory_get_tag_cache_base_address` | `cache_file_read`, `cache_file_tag_cache_contains`, `ps2_cache_mount_cbsp_for_extent`, `scenario_tags_load` | The PS2 cache adapter recognizes the final CE destination by pointer equality; CBSP fixups also need the tag image's final address. It is a simulation/data-ownership API, not a harmless storage convenience. |
| `physical_memory_get_tag_cache_size` | `cache_file_header_verify`, `cache_file_read`, `cache_file_tag_cache_contains`, `ps2_cache_mount_ctag`, `ps2_cache_mount_ctag_with_file_source`, `scenario_structure_bsp_load`, `scenario_tags_load`, `tag_validate_claims_buffer_size`, `tag_validate_tags` | Capacity bounds CTAG parsing/materialization, cache extent validation, and validator claims storage. A zero/unbound size must fail closed; a bootstrap fallback cannot be assumed in the no-bootstrap profile. |

The fresh symbol/caller evidence is stored per-symbol in the rooted closure's
`rooted_link.live_externals` array. For example, `fopen` carries the twelve
sections above and function names; the four getters likewise retain the exact
calling sections. The shared ledger has the corresponding entries and source
candidate paths. It must remain the authoritative machine-readable review set;
this report does not modify it.

## Source-backed behavior and risks

### File-backed stdio

The source callers demonstrate why the family cannot inherit stdout approval.
`main_save_current_solo_map()` opens `z:\last_solo.txt` for writing, and
`main_load_last_solo_map()` later opens it for reading
([`main.c`](../../submodules/halo-ce-universal/source/main/main.c#L1865)). The
framerate/debug path creates or appends `d:\..._init.txt`, formats data with
`fprintf`, flushes, and closes it
([`main.c`](../../submodules/halo-ce-universal/source/main/main.c#L2337)).
`hs_doc()` writes `hs_doc.txt` and unconditionally calls `fprintf`/`fclose`
after its `fopen`, without checking for a null stream
([`hs.c`](../../submodules/halo-ce-universal/source/hs/hs.c#L13851)); this makes
unsupported writes a potential crash, not just a missing optional file.
Error/debug and heap-dump paths use append-mode `d:\` files
([`errors.c`](../../submodules/halo-ce-universal/source/cseries/errors.c#L132),
[`debug_memory.c`](../../submodules/halo-ce-universal/source/cseries/debug_memory.c#L274)).

The parent `hcu_file_bridge` implements a bounded, read-oriented file-reader
interface: it strips only an initial `d:\` prefix and allocates from sixteen
fixed slots ([`hcu_file_bridge.c`](../../src/stream/hcu_file_bridge.c#L9),
[`hcu_file_bridge.c`](../../src/stream/hcu_file_bridge.c#L20),
[`hcu_file_bridge.c`](../../src/stream/hcu_file_bridge.c#L36)). The underlying
PS2 file reader opens with `O_RDONLY` (or `fileXioOpen(..., FIO_O_RDONLY, ...)`)
and fails before FileXio initialization
([`file.c`](../../submodules/halo-ps2/engine/src/stream/file.c#L99)). That is
good evidence for a read-only cache path, but not for Newlib `FILE*` semantics,
`z:\` translation, write/append/flush behavior, or safe failure of `hs_doc`.
The existing file-backed stdio review correctly keeps the family pending
([`hcu-ps2-libc-file-stdio-review.md`](hcu-ps2-libc-file-stdio-review.md#L1)).

**Fresh provider-map finding:** the combined map binds `fopen`, `fclose`, and
`fprintf` to Newlib (`libc_a-fopen.o`, `libc_a-fclose.o`, and
`libc_a-fprintf.o`), and the Newlib `_open_r`/`_close_r`/`_read_r`/`_write_r`/
`_lseek_r` wrappers lead to PS2SDK `libcglue.a` implementations of `_open`,
`_close`, `_read`, `_write`, and `_lseek`, then to PS2SDK EE FileIO (`fio_open`,
`fio_close`, `fio_read`, `fio_write`, `fio_lseek`). `glue.c::_open()` calls
`__path_absolute()` and dispatches through `_libcglue_fdman_path_ops`; the
default PS2SDK path operations are initialized in `ps2sdkapi.c` and use its
FileIO helpers. This proves the provider chain in the exact combined link, but
not that OPL mounted a usable device, that Xbox drive paths are mapped to the
selected root, or that write/append/flush behavior is safe. The PS2SDK path
normalizer preserves explicit device prefixes and defaults relative paths from
`host:`; it does not by itself implement CE `z:\`/`d:\` policy.

**Required before reassessing:** rebind the caller-source hashes (still stale
for `source/main/main.c` and `port/ps2/src/ps2_cache.c`), trace how each CE path
and mode reaches that provider, show deterministic rejection or explicit
supported mapping for `z:\`, `d:\`, and relative paths, and test actual
file-stream open/read/write/append, formatting, flush, EOF/error, close,
null-stream callers, descriptor exhaustion, and repeated lifecycle on each
claimed storage profile (disc and OPL roots as applicable). Unsupported
optional writes must fail without crash or false success. Retain exact ELF,
source hashes, and guest logs. Until then all three rows stay pending.

### Cache-span getters

Current candidate provider source in HCU's PS2 port returns the committed
physical tag/BSP bases and capacities; the tag-size accessor may use the
configured span before allocation, while its no-bootstrap branch returns zero
when neither committed nor configured storage exists
([`ps2_memory.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L238)).
This is the right shape of a caller-owned bounded-span API. The corresponding
current cache adapter requires a non-null tag base and nonzero BSP capacity
before mounting a CBSP and uses the getters to bound destination materializing
([`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L240),
[`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375)).
The existing physical-memory report documents provider/binder fixture coverage
and explicitly says it does not prove retail map fit or lifecycle
([`hcu-ps2-physical-memory-api-review.md`](hcu-ps2-physical-memory-api-review.md#L3)).

The combined optical map now shows all four getter definitions in the exact
rooted closure's `ps2_memory.o` (object SHA-256
`810d4c0e5aa1cdeecb5de86c486b3da19c10322d3472906debce36b0b692c636`), at
`0x00106068`/`0x00106074` for tag base/size and
`0x001060b4`/`0x001060c0` for BSP base/size. Thus the current combined link
does bind the PS2 port owner rather than leaving these providers unresolved.
This still does not establish what addresses/capacities that provider returns
after production startup, whether their backing spans are disjoint and stable,
or whether a retail map fits. The caller-source hash for `ps2_cache.c` remains
stale against the reviewed ledger. Existing unit fixtures compile
provider/caller combinations and assert capacities
([`hcu_ps2_memory_main.c`](../../tests/hcu_ps2_memory_main.c#L125)); they remain
host integration evidence, not target address/lifetime proof.

**Required before reassessing:** refresh the ledger to current caller hashes;
show the exact symbol-provider map from the freshly linked combined ELF (and
ensure there is exactly one owner for each getter); bind base and size to the
same production arena instance before CE allocation; capture target/PCSX2
addresses, capacities, non-overlap/canaries, and unbind/unload ordering; and
run CTAG/CBSP load, validation, failure, and repeated scenario-switch tests
against those exact spans. Retail map high-water/capacity is a subsequent M2
acceptance concern, but no M0 disposition should imply it has been proven.

## Current disposition after exact-root refresh (2026-10-21)

The owner ledger was refreshed with `python3 tools/hcu_ps2_external_review.py
refresh` after the matching host and optical combined profiles were rebuilt
from the exact root. That refresh updated caller-source identities and
invalidated rows whose source/caller identity changed; it did not approve them.

The four cache-span getter rows are now source-backed **implemented** owners in
the current ledger. The host-profile link map binds all four to the exact
closure's `ps2_memory.o` (object SHA-256
`810d4c0e5aa1cdeecb5de86c486b3da19c10322d3472906debce36b0b692c636`). The
source is `port/ps2/src/ps2_memory.c`, SHA-256
`4a9b2bc9a9177c474f8d14d14e41cd7577b3e4382c61c0de40f2950be8637987`: base
getters return the committed physical spans at lines 238–241 and 256–259;
size getters return the corresponding physical sizes or their explicit
pre-allocation configured/zero behavior at lines 243–254 and 261–266. The
allocator promotes configured spans at lines 113–139, and free clears all
spans at lines 207–231. Tests compile the real provider with the parent binder
and assert exact capacities, tag/BSP adjacency, overlap rejection, frozen
bindings, and release/rebind behavior (`tests/test_hcu_ps2_closure.py:57-80`,
`tests/hcu_ps2_memory_main.c:151-174,240-290`). The native ILP32 focused run
passed **3 tests** using the approved outside-sandbox route; the ordinary
sandbox attempt passed 2 and skipped 1 because the sandbox blocks native
execution with SIGSYS. This is source/provider/host-fixture evidence, not
PCSX2 runtime addresses, physical placement, or retail-map capacity.

The `fopen`, `fclose`, and `fprintf` rows remain **pending**. Their exact-root
provider chain is Newlib → PS2SDK libcglue → PS2SDK EE FileIO, but CE `z:\`/
`d:\` and relative-path policy, write/append/flush behavior, OPL mounts, and
null-stream failure handling are untested. PCSX2 did not start the exact
optical ELF in this environment (Qt could not connect to the display; guest
log empty), which provides no stream or guest evidence. Thus this batch now
accounts for 3 pending FILE-stream rows and four reviewed getter owners; no
claim of M0 closure follows.
