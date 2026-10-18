# Gameplay compatibility probe: source audit and entry conditions

Status: M07 is complete for the frozen integer-math closure and the bounded datum-pool closure. Both executed on R5900 in interpreter and recompiler configurations and match the ILP32 host canonical results. This does not establish floating-point equivalence or a general object lifecycle.

## Compared source identities

`config/gameplay-probe-candidates.json` records SHA-256 values and direct includes for seven candidate files from the pinned foundation repositories. Integer math source/header and the datum header are byte-identical between the pins. Random math, datum implementation, and cseries declarations differ; the N64 random math header is absent from the independently pinned OpenCE source tree.

These differences rule out treating the two repositories as interchangeable source packages. The source of record is the pinned halo-64 implementation. The frozen compile list is `integer_math.c`, `integer_math.h`, and `cseries.h`. `cseries.c` is excluded from that list because its include graph is wider than the two symbols `integer_math.c` uses. `random_math` and datum management remain later candidates.

## Important observations

- `source/cseries/cseries.h` defines 30 simulation ticks per second, `boolean` as an unsigned byte, `real` as float, and `tag` as unsigned long. Long and pointer width therefore matter.
- `source/memory/data.h` contains a compile-time `data_iterator` size assertion of 0x10. It contains pointers and long fields; ordinary Linux LP64 layouts are unsuitable for equivalence claims.
- Datum indices combine identifier and absolute-index halves. `data.c` also mixes pointer casts and unsigned-long iterator signatures. Test stale handles, slot reuse, exhaustion, identifier rollover, iterator validity and invalid indices explicitly.
- The independently pinned OpenCE datum implementation has additional release diagnostics, usability checks, and exhausted-array search behavior. These require a semantic review, not a wholesale cherry-pick.
- `random_math.c` includes cseries Windows declarations, real math, geometry, game-engine state and random globals. Initialization allocates a geosphere-derived table and reads platform time. The whole file is not a small standalone RNG module.
- `integer_math.c` is a smaller initial candidate, but still uses diagnostic/formatting services and string routines. Its bit-vector operations rely on 32-bit long semantics.
- The N64 cseries assertion branch does not evaluate assertion expressions. Other release branches preserve expression evaluation because some checks have side effects. Do not define HALO_N64 merely to obtain compilable PS2 code; preserve diagnostic evaluation deliberately under HALO_PS2.
- The N64 prefix explicitly requires big-endian MIPS and imports N64 limits. It is a boundary reference, not a header suitable for direct reuse on PS2.

## Proposed initial ordering

1. Freeze integer-math includes and a minimal diagnostic/CRT boundary with visible failures.
2. Establish type-size and alignment assertions before interpreting any comparison result.
3. Run numerical, rectangle, bit-vector and boundary fixtures on an appropriate host ABI.
4. Port datum management with an explicit allocator boundary after the math and ABI gate.
5. Add deterministic seed operations only after deciding whether to compile the complete random module or a documented source subset. Do not silently substitute another RNG.
6. Expand to a minimal object lifecycle only after its real source closure has been audited.

This is an ordering proposal within M02, not permission to bypass the platform and build prerequisites of M07.

## Host ABI check and executed probe

The initial `gcc -m32` check failed because `bits/libc-header-start.h` was unavailable. Five pinned multiarch packages were then verified and extracted to an ignored private sysroot; they provide the ILP32 compiler/runtime without changing system packages. The harness creates a private source prefix with 32-bit Halo-compatible scalar types and visible diagnostic behavior, compiles the unmodified pinned `halo-64/source/math/integer_math.c` with `-m32`, then executes fixtures for rectangle intersection edges, floor/ceiling log2, integer square roots, and bit-vector word boundaries. The recorded report is `build/gameplay-host32/result.json`.

The probe also compiles a generated negative-control copy with a deliberate `<` to `<=` boundary mutation and requires the fixture to reject it. The checked-in original source is not modified. Both positive and negative controls passed under the approved execution environment. `ceiling_log2(1)` is intentionally excluded because source inspection suggests that it can fail to terminate; its contract and behavior remain unresolved. This probe does not validate the wider Halo ABI, R5900 compiler behavior, target diagnostics, or gameplay runtime.

## Required fixture coverage

- Exact-width integer and bit-vector boundary operations, including counts crossing a 32-bit word.
- Rectangle edges, empty intersections, signed-coordinate boundaries and aliasing where the API permits it.
- Zero/one/power-of-two inputs under explicitly documented function preconditions. Use process timeouts for invalid-domain cases; source inspection suggests `ceiling_log2(1)` can fail to terminate, but this project has not executed that case.
- Datum allocate/delete/reuse, stale identifiers, full pools and deterministic reset.
- Canonical field serialization; no raw pointer/structure dumps as comparison artifacts.
- Explicit seed values and separate deterministic versus platform-time initialization.
- Diagnostic expression evaluation, and failures that cannot be hidden by stubs.

Original defects or undefined-domain behavior require an explicit design decision and retained evidence before any algorithm is changed. REA investigations remain reserved for selected artifacts and questions unresolved by source; none was needed for these source observations.

## M07 execution: visible controls and datum closure

The EE integer-math wrapper has visible PASS/FAIL presentation and explicit assertion-expression evaluation checks. Separate generated boundary-mutation and assertion-failure controls are built from ignored copies. `make test-emulator SCENARIO=probe` runs `tools/test_probe_emulator.py` for all five fixtures in both CPU modes. `python3 tools/qualify_probe.py` rechecks the retained logs.

At parent `9f57c87`, PCSX2 2.8.2, and `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0`:

- Positive integer math, ELF `7917b2cdca5c9b9e40f62998ab46081a95a1b730ca4267611f7228a05f8ab824`, matched `{"fixture":"integer_math","abi":"ILP32","status":"passed"}` with `diagnostics_calls=2`.
- The boundary mutation, ELF `9e9c3ab553aa1988810d4f074fd8820dabe7e879708534d420dd92aec72951b8`, was rejected on the exclusive rectangle edge.
- The assertion control stopped on `probe-diagnostics` assertion `0` and did not report a pass.
- Positive datum, ELF `3613c2999d6a0b032ce5318667521d04482149678e0a79f5b6c2746d8a7db96b`, matched `{"fixture":"datum","abi":"ILP32","slots":4,"status":"passed"}`.
- The stale-handle mutation, ELF `95e9d496bd38242af14bed5877ed973603c9029272f94152a92c4ea68545fb81`, was rejected.

Interpreter and recompiler observations agree for each fixture. The qualification record is ignored `build/emulator/gameplay-qualification.json`. `ceiling_log2(1)` remains unexecuted. Signed identifier shifts retain the pinned implementation.

The datum closure is now `data.c`, `data.h`, and `tag_files.h` from the pinned halo-64 source of record. The whole original implementation is compiled unchanged behind a narrow CRT/allocation boundary. `csstrncpy` calls an out-of-line wrapper with the original `strncpy` semantics: the two-byte name-derived identifier seed is intentionally not a C string. This avoids misclassifying intentional bounded copying as a compiler truncation error. Diagnostic checks remain active; allocation failure is explicit.

`python3 tools/build_datum.py --host` passes a bounded ILP32 fixture for allocation failure, four-slot exhaustion, stale lookup, slot reuse, iteration, explicit-index allocation, reset, invalidation/revalidation and identifier rollover. Layout assertions require a 56-byte datum array, signature offset 40, storage-pointer offset 52, and a 16-byte iterator. `python3 tools/build_datum.py` builds its EE counterpart, and that counterpart has now executed. These checks do not establish general object lifecycle correctness or floating-point equivalence. Signed identifier shifts and narrowing retain the pinned implementation. The target runs above are the check for those shifts; they are not a portable ISO C rewrite.

The datum negative control generates an ignored copy that deliberately disables identifier mismatch rejection. The host fixture rejects it after slot reuse; arbitrary crashes do not qualify. `python3 tools/build_datum.py --host --negative-control` records that rejection. EE positive/negative controls are built independently with `--negative-control` selecting the latter. The frozen closure hashes are recorded in `config/gameplay-probe-candidates.json`.
