# Gameplay compatibility probe: source audit and entry conditions

Status: the M02 integer-math compile closure is frozen. The original `integer_math.c` has been compiled and executed in a bounded ILP32 Linux harness. The closure compiles and links for R5900; execution remains M07 work. This host result does not establish R5900 behavior.

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
