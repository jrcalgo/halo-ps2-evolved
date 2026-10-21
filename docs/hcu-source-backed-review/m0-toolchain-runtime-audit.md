# M0/M4 EE compiler and C-runtime owner audit

Date: 2026-10-20. This audit follows the current combined host-profile link
report in `build/hcu-parent-link-probe/result.json` and supports M0 external
review and Desktop-plan M4 ABI/interface work. It does not claim target runtime
qualification: the current PCSX2 attempt could not initialize a display.

## Source and binary identity

- HCU rooted object: `build/hcu-ps2-closure/all/rooted.o`, SHA-256
  `4a6dc9b2fb90dbe1f13f5d9f29c4e3c0593d731cb720dc29`.
- Combined machine ELF: `build/hcu-parent-link-probe/hcu-gameplay-machine.elf`,
  SHA-256
  `38dc08dcd642aeb8ab5fafd73ccdc3dd517d212585413f0e597f4d840f121e39`.
- Link map: `build/hcu-parent-link-probe/hcu-gameplay-machine.map`.
- EE toolchain is built from `submodules/ps2toolchain-ee` at
  `657b9e646920fda447079be56d915eb4f8a33c25`. The staged EE GCC and Newlib
  sources are `build/toolchain/sources/ps2toolchain_ee_gcc` at
  `df77d03bc1bd5765b40de554918a5ff541202548` and
  `build/toolchain/sources/ps2toolchain_ee_newlib` at
  `8881dc4b138f0561596980ac9a481c7e638aebd0`.

## Per-symbol owner and semantics

| Rooted external | Actual current combined-link provider | Source evidence and semantic role | Open qualification |
|---|---|---|---|
| `__extendsfdf2` | EE `libgcc.a(_sf_to_df.o)` | GCC `libgcc/soft-fp/extendsfdf2.c` unpacks the IEEE single, extends it to double, and repacks double. Used by CE float expressions promoted to `real`/double under this ABI. | Software-double cost is real; keep semantics unchanged. Add EE numeric vectors/profile cost before any replacement. |
| `__fixdfsi` | EE `libgcc.a(_df_to_si.o)` | GCC `libgcc/soft-fp/fixdfsi.c` unpacks double and converts to signed integer via `FP_TO_INT_D`; CE conversion sites include `fast_ftol` and color conversion. | Verify representative negative/fractional and boundary values on EE; no hand-written fast conversion is substituted. |
| `__truncdfsf2` | EE `libgcc.a(_df_to_sf.o)` | GCC `libgcc/soft-fp/truncdfsf2.c` initializes the configured rounding mode, truncates double to single and repacks the result. | Numeric edge vectors and timing remain unmeasured on EE. |
| `floor` | EE `libm.a(libm_a-s_floor.o)` | Newlib `newlib/libm/math/s_floor.c`; rooted CE callers include animation keyframe selection, time updates and geometry quantization. | Target negative/fractional and large-value vectors pending. |
| `fmod` | EE `libm.a(libm_a-w_fmod.o)` | Newlib `newlib/libm/math/w_fmod.c` wrapper dispatches to IEEE remainder implementation; rooted callers include periodic functions, animation, weapon first-person update and vehicle update. | Target sign, exact-multiple and zero-divisor behavior pending. |
| `rint` | EE `libm.a(libm_a-s_rint.o)` | Newlib `newlib/libm/common/s_rint.c`; used through CE `fast_ftol`/pixel conversion inline paths. Its result follows the active rounding mode. | Confirm EE rounding mode and ties with a target fixture. |
| `sqrt` | EE `libm.a(libm_a-w_sqrt.o)` | Newlib `newlib/libm/math/w_sqrt.c` wrapper dispatches to IEEE sqrt; live CE callers span movement, AI, collision and geometry. | Target positive, zero, negative and NaN behavior plus EE timing pending. |
| `memcpy` | EE `libc.a(libc_a-memcpy.o)` | Newlib `newlib/libc/string/memcpy.c`; standard non-overlapping byte copy used throughout CE data, object, input and render paths. | Target overlap/bounds are caller preconditions; actual EE copy vectors remain pending. |

The link map has concrete archive-member records and final symbol definitions for
all eight entries; none is a typed-zero `ps2_platform.c` implementation. The
rooted caller identities remain authoritative in
`docs/hcu-source-backed-review/hcu-ps2-external-review.json`; the very broad
caller candidate lists for compiler helpers must not be interpreted as one
specialized call path. The archived runtime is a real owner, not an exclusion
and not a platform no-op.

## Automated regression and current limits

`tests/test_hcu_ps2_toolchain_runtime_owners.py` pins the eight current linked
providers in the production machine map and rejects the same names appearing
as generated platform bodies. This proves provider ownership for that exact
build map, not numerical conformance on the EE. Run it after rebuilding the
combined image. Current host ABI/codegen and interface tests pass, but guest
verification has not: the latest PCSX2 attempt returned before guest entry
with exit 127 because the AppImage exposes only Wayland/XCB Qt plugins; the
offscreen plugin is unavailable, and Xvfb could not create its X socket in the
shared `/tmp/.X11-unix` directory. Do not transfer the prior image's
`memory-ready` evidence to this ELF.

The ledger now records all eight as `implemented` in
[`hcu-ps2-toolchain-eight-review.md`](hcu-ps2-toolchain-eight-review.md).
`tools/hcu_ps2_external_review.py check` closes on the 322-symbol rooted
object. EE timing and extra numeric vectors remain M6. This audit's provider
table is the link evidence for that review; it is not a guest run. M4 still requires
the current-image startup guest boundary, live controller evidence, and an
honest presentation/runtime consumer. No rendered scene or M4 completion is
claimed.
