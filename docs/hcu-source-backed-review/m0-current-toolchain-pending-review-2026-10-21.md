# M0 review of the 31 pending toolchain externals

Date: 2026-10-21. Scope: exactly the 31 `classification: toolchain`,
`disposition: pending` rows in the source-backed external ledger at review
time. This is a report-only source/provider audit. No ledger, plan, or
production code was modified, and no row is approved by this report.

## Evidence identity and currentness

The reviewed root is
`build/hcu-ps2-closure/all-no-bootstrap-memory/rooted.o`, SHA-256
`f1a169d679ee354044390083945b9e74319ca0b833b01da25ff904f3ea1f5e3a`.
The refreshed closure `result.json` reports 369 compiled units, 0 failed
units, and 322 rooted live externals. The ledger at
`docs/hcu-source-backed-review/hcu-ps2-external-review.json` records this same
root SHA. I compared each of the 31 ledger `caller_sections` arrays to the
matching `rooted_link.live_externals` entry: all 31 arrays match exactly. I
also recalculated the SHA-256 of every ledger `caller_sources` file against
the checked-out `submodules/halo-ce-universal` source tree: there are zero
missing files and zero hash mismatches across these 31 rows. This supersedes
older statements in prior reports that some of these caller hashes were
stale, but it does not update those reports or change ledger dispositions.

The exact combined optical-profile diagnostic is bound through
`build/hcu-parent-link-probe/result-optical.json` (SHA-256
`213f7dbbcb868a334e43e218b2475c1c3256c7ee1d89e723d4741abd9953db20`). Its
`source_inputs.hcu_rooted_sha256` is the root above. The linked machine ELF
SHA-256 is
`019dbd3a328f92756ed5a0d34011be13593ad7cf5d90c4bc5a203a65b98fadec`; its
link-map SHA-256 is
`f8e8f522751db06e8cd8caf15a661e94c1bac9efccb7b2d65a65c5f6621cf6b1`.
That map has zero unresolved imports but the probe reports `acceptance: false`;
it is a diagnostic link, not a runtime or M0 sign-off.

Source provenance is pinned in `config/toolchain-sources.json`: EE GCC
`df77d03bc1bd5765b40de554918a5ff541202548`, Newlib
`8881dc4b138f0561596980ac9a481c7e638aebd0`, and PS2SDK submodule
`4960c2e2bf65c5ea4b604d1a41766a82f97b104e`. The exact installed archive
hashes used for the checked map are:

| Archive | SHA-256 |
|---|---|
| EE `libgcc.a` | `301ee093e36867ebbabf460745a881548d4d68f457828033dada6d1079549046` |
| EE Newlib `libc.a` | `24ff16cd8a2cfbdd8960699b173bdc21fadc51f2df1cc2ff0fc433a4b745b51b` |
| EE Newlib `libm.a` | `b7069a907b2d5b332246604d4c52433a14b816e50aca38d80f60fc7991a7f4bc` |
| PS2SDK EE `libcglue.a` | `00f49c95aadd7d80811cb58083a2f52be689fac95ff44a496a96b7dbca435162` |

The PS2 CRT compatibility bodies live in
[`ps2_crt.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_crt.c),
SHA-256 `394626e000556a2e37bc7091b030770d8f5e5da10b656230938f86f14caf09e2`.
These are archive and source-tree identities, not proof that the routines
match every CE/Xbox caller contract.

## Caller and provider inventory

Caller counts below are exact rooted function counts derived from the
refreshed closure; representative names are provided to explain semantics,
not to replace the full exact caller lists in the ledger and closure report.
The fresh combined map and `nm` show the selected implementation owner for
each symbol. “Selected provider” answers where the code comes from; the
following sections state why that alone is not sufficient for approval.

| Symbol | Callers | Fresh selected provider | Live caller semantics / risk |
|---|---:|---|---|
| `__divdf3` | 12 | GCC EE `libgcc.a(_div_df.o)` | Double division in biped/collision physics, input, observer, device/game-engine, and `main_loop` work; numerical edge cases and high-frequency EE cost matter. |
| `__extendsfdf2` | 240 | GCC EE `libgcc.a(_sf_to_df.o)` | Float-to-double promotion across AI, animation, physics/collision, weapons, effects, camera, and render calculations; a pervasive simulation dependency. |
| `__fixdfsi` | 4 | GCC EE `libgcc.a(_df_to_si.o)` | Integer conversion in `fast_ftol`, RGB/ARGB conversion, and sound gain; depends on rounding/conversion rules. |
| `__floatdidf` | 1 | GCC EE `libgcc.a(_floatdidf.o)` | 64-bit integer conversion in `main_loop`; exact precision and overflow semantics should be checked. |
| `__floatdisf` | 2 | GCC EE `libgcc.a(_floatdisf.o)` | Integer conversion in `main_loop` and object function-value calculations. |
| `__gtdf2` | 5 | GCC EE `libgcc.a(_gt_df.o)` | Double comparison in piecewise evaluation, item alignment, frame-rate/debug values, animation ping, and vehicle export. |
| `__truncdfsf2` | 163 | GCC EE `libgcc.a(_df_to_sf.o)` | Double-to-float narrowing throughout movement, collision, AI, animation, weapon/projectile, vehicle, and render calculations. |
| `_snprintf` | 13 | HCU PS2 `ps2_crt.o` (`ps2_crt.c`) | CRT compatibility adapter is used by AI descriptions/indexing, profile enumeration, mutex naming, `main_loop`, and frame presentation. It forwards to Newlib `vsnprintf`, so truncation/return semantics may differ from MSVC `_snprintf`. |
| `_stricmp` | 27 | HCU PS2 `ps2_crt.o` | ASCII-only case folding in AI strings, animation names, navigation points, and HaloScript identifiers; not locale/code-page aware. |
| `_strnicmp` | 4 | HCU PS2 `ps2_crt.o` | Bounded ASCII-insensitive comparison for encounter/platoon/squad and script-token names. |
| `atan2` | 16 | Newlib `libm.a(libm_a-w_atan2.o)` plus `libm_a-e_atan2.o` | Actor visibility, convex hull, Euler conversion, teleporter, input, and object/game-engine logic; quadrant, signed-zero, infinity/NaN behavior and cost need tests. |
| `exit` | 1 | Newlib `libc.a(libc_a-exit.o)` | Sole caller is CE `halt_and_catch_fire`; this is fatal-control-flow behavior, not an ignorable utility. It must not resume gameplay or return to a damaged call chain. |
| `fclose` | 11 | Newlib `libc_a-fclose.o`; reaches the Newlib/PS2SDK file stack | Closes CE streams used by cheats, console, debug dumps, camera files, docs, framerate, and last-map paths. Must release descriptors, flush as specified, and preserve errors. |
| `fflush` | 4 | Newlib `libc_a-fflush.o`; reaches stream write path | Explicit flush in lens-flare temporary output, allocation records, framerate output, and error logs. This is stateful I/O and can fail. |
| `fopen` | 12 | Newlib `libc_a-fopen.o`; `_open_r` → PS2SDK libcglue/FileIO | Callers request `d:\` and `z:\` paths, read/write/append modes, and relative files. Device root selection and unsupported writes are not proven. |
| `fprintf` | 9 | Newlib `libc_a-fprintf.o` | Formats into FILE streams for dumps, camera save, allocation records, `hs_doc`, framerate, and errors; a file sink is not the separate stdout contract. |
| `fread` | 1 | Newlib `libc_a-fread.o`; reaches PS2SDK file path | `main_load_last_solo_map` reads a persisted map selection. EOF, short read, path, and saved-data validity semantics affect startup state. |
| `memcmp` | 4 | Newlib `libc.a(libc_a-memcmp.o)` | CE `csmemcmp`, CBSP/CTAG signature checks, and input-state publication; correct ordering and exact byte extent required. A previous review document claims approval, but this current ledger row is pending and must be reconciled centrally. |
| `memcpy` | 136 | Newlib `libc.a(libc_a-memcpy.o)` | Broad active consumers include AI/action structures, colors, input, geometry, parsing, and render state. Newlib code identity is confirmed; overlap precondition and every size/bounds owner remain unaudited. |
| `memset` | 38 | Newlib `libc.a(libc_a-memset.o)` | CE input, multiplayer variant construction, and many initialization/clear operations. Correct fill byte and destination extent must be preserved. A prior review document claims approval, but the current ledger row is pending. |
| `printf` | 8 | Newlib `libc.a(libc_a-printf.o)` | Cache loading, assertions/fatal diagnostics, shell initialization, HaloScript, and map load use stdout; output destination/flush behavior is part of diagnostics and failure observability. |
| `puts` | 6 | Newlib `libc.a(libc_a-puts.o)` | Game load, precache, shell, map-load, and `main_loop` messages; must confirm stdout route and line termination on target. |
| `qsort` | 12 | Newlib `libc.a(libc_a-qsort.o)` | Sorting actor/encounter candidates, aim assist, local players, lens-flare data, and HaloScript symbols; comparator ordering/tie stability can affect choices and generated presentation data. |
| `rint` | 3 | Newlib `libm.a(libm_a-s_rint.o)` | `fast_ftol` and RGB/ARGB conversions. Result follows rounding-mode semantics; intended CE/Xbox round-to-nearest behavior is not demonstrated by archive identity. |
| `snprintf` | 9 | Newlib `libc.a(libc_a-snprintf.o)` | HaloScript parsing/inspection, tags, object creation, diagnostics, and validation use bounded output. Format support, truncation/NUL, return count, and buffer capacities need vectors. |
| `sprintf` | 44 | Newlib `libc.a(libc_a-sprintf.o)` | Many AI/HaloScript/debug/name/object paths write formatted strings; unbounded destination sizes and MSVC format differences need caller-buffer review. |
| `sqrt` | 66 | Newlib `libm.a(libm_a-w_sqrt.o)` plus `libm_a-e_sqrt.o` | Distances, normalization, collision, AI movement, player control, projectile and vehicle calculations; hot simulation use requires numerical parity and EE performance evidence. |
| `strchr` | 6 | Newlib `libc.a(libc_a-strchr.o)` | AI debug, text/error parsing, HaloScript compilation, and unit dialogue. NUL search and high-byte behavior should be tested. |
| `strcpy` | 5 | Newlib `libc.a(libc_a-strcpy.o)` | AI communication, HaloScript inspection, and DirectSound end-scene string paths; destination capacity is caller-owned and not established by implementation provenance. |
| `strrchr` | 9 | Newlib `libc.a(libc_a-strrchr.o)` | AI/script index lookup, console completion, tag-name path stripping, damage, and dialogue naming; empty/no-match and separator handling matter. |
| `strstr` | 14 | Newlib `libc.a(libc_a-strstr.o)` | AI debug, sound class commands, variant selection, HaloScript name search, last-map lookup, saved-game directory and vehicle seat paths. Matching semantics are pure, but caller interpretation/path correctness is not verified. |

The seven `__*` arithmetic/conversion entries are GCC ABI routines from the
pinned compiler library, not generated HCU platform stubs. `rint`, `sqrt`, and
`atan2` are Newlib math-library providers. The `mem*`, string, sorting,
formatting and FILE-stream entries are Newlib providers. The three underscore
compatibility entries are project port code and need their own contract tests.

## Stateful boundaries: why the distinction matters

### File-backed Newlib stdio is not the bounded cache reader

The fresh map binds Newlib `fopen`, `fclose`, `fflush`, `fprintf`, and `fread`
to real Newlib members. `fopen`'s reentrant implementation then calls
`_open_r`; the map resolves the lower-level `_open`/`_close`/`_read`/`_write`/
`_lseek` path through PS2SDK libcglue and EE FileIO. This is distinct from the
parent's fixed-slot, read-only `hcu_file_bridge`/FileXio reader. Consequently,
the library implementations do not establish the mounted OPL/optical device,
CE `d:\`/`z:\` translation, writable/append policy, or safe handling by
callers such as `hs_doc` that do not check a failed open before formatting.
Keep all five FILE-stream rows pending until source paths and modes are tested
through the exact guest image against each claimed storage profile. Tests need
open/read/write/append/flush/close, error/short-read/EOF, failed-open callers,
descriptor exhaustion/reuse, repeated lifecycle, and explicit rejection or
mapping of Xbox/relative roots. The existing seven-row file/cache report
contains useful details for `fopen`, `fclose`, and `fprintf`, but this review
adds `fflush` and `fread` from the current 31-row set.

`printf` and `puts` are also real Newlib routines, but they travel through the
stdout stream rather than the cache bridge. Keep their stdout/console route
distinct from file-backed `fprintf`; demonstrate that diagnostics and fatal
messages reach the intended PS2 output sink, and distinguish a lost message
from a lost state transition. No target-side stdout capture is part of this
source/provider comparison.

### Pure library algorithm is not automatically a CE parity pass

Memory, string, sorting, and math implementations have no machine-device
ownership of their own, but their callers still own bounds, ordering, locale,
rounding, and corner-case assumptions. `memcpy` is especially important:
the 136 live caller functions include real structure/data copies, so it must
not be treated like `memmove`; establish non-overlap and length validity for
all callers or identify/fix the unsafe callers before approval. `sprintf` is
unbounded by definition, so no source archive can prove output-buffer sizing.
`qsort` may reorder equal values; comparator and tie behavior must be compared
to CE where an order feeds simulation decisions. `rint` is sensitive to
floating-point environment, while the EE software double helpers preserve
source double-expression behavior and may be expensive. Do not replace them
with single precision as a presumed optimization.

The current ledger's `memcmp` and `memset` entries are pending even though
[`hcu-ps2-libc-memory-review.md`](hcu-ps2-libc-memory-review.md) says those
two were approved in an earlier review pass. This is a ledger/report
consistency issue, not grounds for this report to change them. A central
ledger refresh must either restore those prior dispositions with their
appropriate source/test evidence or explicitly explain why the status regressed.
The same central reconciliation should verify any overlap between the 31
pending rows and older batch reports before counting M0 progress.

## Disposition and required evidence

All **31/31** rows remain pending in the authoritative ledger after this
review. Provider identity is now current and reproducible for the exact
root-linked optical diagnostic; all source hashes and caller section sets
also match the current root. This substantially improves provenance quality,
but it does not furnish semantic owners/tests and the diagnostic probe itself
still has `acceptance: false`.

Recommended next evidence, without changing the current dispositions here:

1. Add a machine-checked regression that verifies the current rooted hash,
   equality of the complete 31 caller-section sets, equality/freshness of all
   source hashes, and the exact selected provider/member for each row in the
   combined map. Ensure provider tests accept the intended `ps2_crt.o` adapter
   only for `_snprintf`, `_stricmp`, and `_strnicmp` and reject generated empty
   replacements.
2. Resolve the pending-vs-prior-approved `memcmp`/`memset` ledger conflict;
   retain `memcpy` pending until its non-overlap and size audit covers the 136
   current callers.
3. Add target/PCSX2 vectors for GCC conversions, IEEE math, `rint` rounding,
   string/byte primitives, `qsort` comparators, and formatting. Vectors must
   compare CE/source contracts rather than simply calling the same Newlib
   implementation twice. Measure representative hot EE math paths before
   proposing any precision change.
4. Qualify FILE streams and stdout on the exact guest artifact, with explicit
   device/root and read/write policy, then bind those results to its ELF,
   archive hashes and runtime log. Exercise fatal `exit` in a controlled
   harness and prove it never returns into gameplay.
5. Review each CE buffer/length/caller contract for `sprintf`, `strcpy`, and
   `memcpy`; standard-library implementation identity cannot supply a bound
   that the source caller does not enforce.

Halo-64 is not used as the implementation owner here. Its N64 runtime serves
only as a platform-comparison reference; it cannot establish R5900 library
behavior, CE caller compatibility, or this port's file/storage semantics.
