# Gameplay compatibility probe: source audit and entry conditions

Status: M02 candidate audit. No Halo gameplay module has been compiled or executed by this project, and M07 has not started.

## Compared source identities

`config/gameplay-probe-candidates.json` records SHA-256 values and direct includes for seven candidate files from the pinned foundation repositories. Integer math source/header and the datum header are byte-identical between the pins. Random math, datum implementation, and cseries declarations differ; the N64 random math header is absent from the independently pinned OpenCE source tree.

These differences rule out treating the two repositories as interchangeable source packages. The candidate source of record is the pinned halo-64 implementation, with changes compared to OpenCE individually before adoption. A complete transitive include/link closure is still pending.

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

## Host ABI check

A temporary `gcc -m32` program including standard integer and I/O headers failed during compilation because `bits/libc-header-start.h` is unavailable. The test did not reach linking or execution. Appropriate 32-bit libc development support is a prerequisite for the normal pointer-sensitive host harness. No package was installed.

## Required fixture coverage

- Exact-width integer and bit-vector boundary operations, including counts crossing a 32-bit word.
- Rectangle edges, empty intersections, signed-coordinate boundaries and aliasing where the API permits it.
- Zero/one/power-of-two inputs under explicitly documented function preconditions. Use process timeouts for invalid-domain cases; source inspection suggests `ceiling_log2(1)` can fail to terminate, but this project has not executed that case.
- Datum allocate/delete/reuse, stale identifiers, full pools and deterministic reset.
- Canonical field serialization; no raw pointer/structure dumps as comparison artifacts.
- Explicit seed values and separate deterministic versus platform-time initialization.
- Diagnostic expression evaluation, and failures that cannot be hidden by stubs.

Original defects or undefined-domain behavior require an explicit design decision and retained evidence before any algorithm is changed. REA investigations remain reserved for selected artifacts and questions unresolved by source; none was needed for these source observations.
