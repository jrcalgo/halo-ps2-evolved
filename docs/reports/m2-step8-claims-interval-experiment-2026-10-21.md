# Step 8 exact claims interval experiment

The bounded C candidate exactly replayed **226,395 operations from the real CE validator** during the a30/a50 package transaction fixture. Its peak was **4,820 merged intervals**, or 38,560 bytes of two-u32 interval payload. A fixed 8,192-record table (65,536 payload bytes) accommodated the complete captured trace without exhaustion. This supplies a concrete replacement candidate for the validation bitmap. The immediate integration target is multiplayer Longest/Blood Gulch and then the stock multiplayer corpus. This experiment does not establish production memory fit or target acceptance.

## Implementation and reproduction

[`tools/hcu_claim_interval_experiment.py`](../../tools/hcu_claim_interval_experiment.py) implements exact half-open interval claims, byte membership/range intersection, BSP-domain clearing including interval splitting, adjacency merging, and checked 32-bit ranges. Capacity failure preserves the previous set. Ordinary overlap failure preserves CE's existing behavior, including its whole-word branch: a complete aligned 32-byte word is checked before any byte in that word is claimed. If byte 40 is already occupied, `claim(0,64)` claims only `[0,32)` before returning false. Tests explicitly cover conflicts at byte 1, 31 and 40, unaligned starts, and partial trailing words.

The actual bounded C backend is [`ps2_claim_intervals.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_claim_intervals.c), declared in [`ps2_claim_intervals.h`](../../submodules/halo-ce-universal/port/ps2/include/ps2_claim_intervals.h). It has no allocator or static payload storage. The caller provides the interval table and context. Binary searches locate records; insert/merge and clear mutate only affected tails using `memmove` after capacity checks. A clear that would split a full table fails before changing entries. Return values distinguish success, overlap and invalid/exhausted storage.

The Python and C tests include 12,000 and 40,000 deterministic operations against byte-bitmap models. A further test compiles the production `claim()` function verbatim with a bounded test-address provider and compares 30,000 operations with the candidate, checking every byte periodically. This direct source-function oracle guards against accidentally duplicating an incorrect interpretation of CE's whole-word branch.

The retail mode transforms a temporary copy of the actual included [`tag_validate.c`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L477). It wraps original claim, unclaim, single-byte membership and range-membership implementations, logging their normalized offsets and original results. It records actual domain resets at the bitmap reset. The production file and shared fixture are untouched. It compiles and runs the existing package-backed native ILP32 fixture using the transformed include in a temporary copy of its C entry. Source-seam checks and rejection of absent reset/claim operations prevent silent success on an empty trace. A skipped native fixture is treated as failure.

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 tools/hcu_claim_interval_experiment.py --retail --trace /tmp/new-hcu-claims.trace

python3 tools/hcu_claim_interval_experiment.py \
  --trace build/hcu-claims-experiment-20261021/retail.trace --capacity 8192
python3 -m pytest -q tests/test_hcu_claim_interval_experiment.py
python3 -m pytest -q tests/test_hcu_claim_interval_c.py
python3 tools/hcu_claim_interval_c_replay.py \
  build/hcu-claims-experiment-20261021/retail.trace
```

Use a fresh trace name. The first sandbox run correctly failed after SIGSYS skips; the successful native experiment ran with approved execution outside that sandbox. Native test result: **1 unittest passed**, including both a30/a50 package subtests, **151.471 seconds**. This is the host ILP32 consumer/transaction fixture with deliberately oversized tag and BSP buffers.

## Measured results and identities

| Trace operation | Count |
|---|---:|
| Domain resets | 5 |
| Claims | 209,834 |
| Range membership queries | 16,459 |
| BSP-domain range clears | 97 |
| Single-point membership queries in retail trace | 0 |

All 226,395 operations replayed without a return-value mismatch. Single-byte membership is covered by the independent randomized fixture, rather than an actual retail call in this trace. The original bitmap's maximum configured capacity was 3,145,728 bytes (24 MiB address domain / 8); that value derives from the **host fixture**, and is not the PS2 production claims size. The candidate's measured peak pair payload is 38,560 bytes, while an 8,192-entry fixed-capacity implementation would reserve 65,536 bytes plus actual count/capacity/bookkeeping and any update workspace. Python's object allocations are not that C target store; no Python memory statistic is presented as an EE allocation.

The Python diagnostic uses sorted-vector copies. Its conservative comparison/copy work counter was **869,167,737**, and one complete host Python replay took **4.445 seconds**. The C backend instead performs **2,704,899 binary-search/clear comparisons** and moves **50,580,119 interval records / 404,640,952 bytes**, cumulatively over all five domain resets and repeated transaction cases. Host compile plus ctypes replay took **0.400 seconds** in one run. These figures are not EE cycles; load-time memory traffic requires target measurement. The captured trace proves the candidate's semantics and a30/a50 interval count.

The same backend compiles successfully for R5900 with `-O2 -std=gnu89 -Wall -Wextra -Werror`; the standalone object contains 1,936 text bytes, zero data and zero BSS. [`tests/hcu_claim_interval_layout.c`](../../tests/hcu_claim_interval_layout.c) also compiles with the target compiler, proving an eight-byte interval, 40-byte context and counter offset 24. Thus an 8,192-entry target table plus its context consumes **65,576 caller-owned bytes**, before any enclosing arena alignment/guard. The clear routine has two eight-byte local fragments; ordinary scalar/call stack remains a measured stack obligation. This proves object compilation and layout, not guest execution.

Retained generated artifacts are in `build/hcu-claims-experiment-20261021/`:

| Artifact | SHA-256 |
|---|---|
| `retail.trace` | `2e115f48f1f845333f4b1dfcde18ffd36e3b43e545650a2d8468d541f9516358` |
| temporary compiled fixture `main.c` | `4115024ce8ba7f4999c46633ccb0618286f9b6b212f3f79d9b800e391ba2fc46` |
| temporary `tag_validate_instrumented.c` | `1e0e23391599d787c422f417de93efdf9c4e6b99b61f2a44dd5562155d030b0e` |
| underlying production validator | `750928041f687eb612e5af70df37fde81c7601ca773454886582cd32c0bee9cc` |
| experiment tool after whole-word correction | `776e1ca281ac89f39a7854754c388cd043c5d40432c7d9c4c570211718c9a5c3` |
| Python candidate unit tests after whole-word correction | `2f6fb61097901f7340bc82c4ea93ceae6dc410a48ad3d1076cd07c0e94abdd5c` |
| C backend | `f4ed74ec44010805829b25833443d71709094ad46d147f20ec5ae94108419706` |
| C backend header | `b1c6c6032dec4c54e3ca16ad15726ae9b25150c6e7959d3d75f22e32eb0c594a` |

The fixture was copied before the main agent's concurrent whole-BSP SHA256 snapshot strengthening; the retained compiled copy identifies what this run tested. The trace instrumentation itself preserves all original validator results. The retail fixture Python hash observed during the run was `14af200645ea1f935a29123d10b45c2b7741bb0c7ac47b755d749ef1d9c7060d`. Subsequent invocations of the tool also write a trace identity sidecar automatically.

## Next production slice and remaining gates

Integrate the C backend behind an explicit diagnostic configuration and caller-owned arena binding; the replay and source-core differential now pass before that integration. Capture Longest/Blood Gulch and the stock multiplayer corpus before choosing a multiplayer product capacity; 8,192 is currently only the tested a30/a50 cap. Preserve retained tag claims across BSP clears, empty/map-reset behavior, byte-exact overlap detection, checked offsets, all failure paths and the current map transaction rules. Measure target cycles under worst insertion/clear patterns. Campaign-wide capture and residency remain subsequent broader-product requirements.

This experiment makes the claims route in [the owner analysis](m2-step8-game-state-claims-owner-route-2026-10-21.md) actionable. Even zero-byte claims cannot solve the whole-machine D20 lower bound once the excluded runtime duties are charged. The separate animation/BSP residency design and complete owner/target evidence are still required. Halo-64's stateful rendering and retained lightmap-query notes remain useful comparative evidence ([N64 notes:35](../../submodules/halo-64/port/n64/NOTES.md#L35)); its reduced-feature pools do not authorize PS2 savings. These questions are proved from available source and native tests; REA is unnecessary for this slice.
