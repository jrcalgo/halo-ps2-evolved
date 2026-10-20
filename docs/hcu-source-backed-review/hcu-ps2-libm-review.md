# M0 pinned Newlib libm review

## Reviewed API set

This review covers rooted `acos`, `asin`, `atan2`, `ceil`, `cos`, `floor`, `fmod`, `log10`, `pow`, `sin`, `sqrt`, and `tan`. The current combined R5900 link map resolves these to the pinned EE Newlib `libm.a` members: wrapper `w_*` objects for acos/asin/atan2/fmod/log10/pow/sqrt and `s_*` objects for ceil/cos/floor/sin/tan. The Newlib source pin is `8881dc4b138f0561596980ac9a481c7e638aebd0` (`ee-v4.6.0`) in [`toolchain-sources.json`](../config/toolchain-sources.json#L19). They are real pinned mathematical implementations, not generated platform stubs.

The rooted CE callers place these operations on simulation and presentation math paths: actor/camera angles, object/effect transforms, periodic animation and weapon state, damage/effect attenuation, and structure lens flares. The PS2 engine does not replace their formulas or force single precision here; arguments/results retain the CE `real`/ABI semantics, with the existing EE compiler/runtime support. The source audit does not prove bit-for-bit Xbox floating-point output. M6 must compare deterministic vectors and combat/animation state with the CE reference, and profile double-heavy hotspots before any numerical substitution.

`rint` remains pending because its behavior depends on current rounding mode and the rooted calls include conversion helpers; `rand` remains pending because its state/sequence is behaviorally significant. This report approves only the 12 standard libm owners and their current source-level API contracts. `test_pinned_newlib_libm_helpers_resolve_to_exact_archive_members` asserts each exact archive member in the accepted combined map and ties its ledger entry to this report; it is provider/source evidence, not a numerical parity test.
