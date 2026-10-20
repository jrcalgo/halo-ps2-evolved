# Toolchain remainder: formatting, exit, memory, sort, and rounding

Status: `exit` is the pinned Newlib process terminator on the halt fallthrough. The other ten rooted names stay pending. Provider identity is not a caller-contract approval.

## Narrow and wide formatting

`_snprintf` and `_vsnprintf` are real PS2 CRT wrappers. They forward to Newlib `vsnprintf` (`port/ps2/src/ps2_crt.c:42-55`). That is not the MSVC `_snprintf` contract: C99 `vsnprintf` returns the length that would have been written and always stores a terminator when `count > 0`, while the Xbox callers also pass `capacity - 1` and sometimes test the return. The numeric-format review already kept these names out of the `snprintf`/`vsnprintf` approval.

`_vsnwprintf` does not format. It copies the format string into the destination and ignores the argument list (`ps2_crt.c:58-73`). `usnprintf` and `uvsnprintf` in `source/text/unicode.c:1339` and `:1493` are the live callers, so UI and script wide text would lose its substitutions.

`vswprintf` is linked from Newlib `libc_a-vswprintf.o`. Newlib declares `vswprintf(wchar_t *, size_t, const wchar_t *, va_list)` (`newlib/libc/include/wchar.h:289`). CE `usprintf` and `uvsprintf` call `vswprintf(string, format, arglist)` with no size (`source/text/unicode.c:1468,1514`). The format pointer is passed where Newlib reads a count. That call shape is not approved.

## Process exit

`halt_and_catch_fire` draws the fatal screen in `while (TRUE)` and then calls `exit(0)` (`source/main/main.c:3197-3280`). The rooted section is `.text.halt_and_catch_fire`. The combined map resolves `exit` from `libc_a-exit.o`. Reaching that call ends the process after the halt screen; it is not a simulation service. The infinite loop is the screen itself. `exit` is the source fallthrough that terminates if that loop is left.

## Calls that stay pending

| Symbol | Live caller | Why it stays pending |
|---|---|---|
| `memcpy` | 133 rooted sections, including `csmemcpy` | `csmemcpy` asserts non-overlap and then calls `memcpy` (`source/cseries/cseries.c:596-605`). Direct callers are not all covered by that assert. The memory review already identified Newlib `libc_a-memcpy.o` and withheld approval. |
| `qsort` | aim assist, actor perception, vehicle scripting, object and lens-flare ordering | Newlib `libc_a-qsort.o` is linked. `source/game/aim_assist.c:525` sorts gameplay targets. Equal-key order is not proven against the Xbox CRT (`hcu-ps2-ascii-compare-review.md`). |
| `strtok` | `csstrtok` | `csstrtok` returns `strtok(s1, s2)` (`source/cseries/cseries.c:554-560`). `cseries.h` also defines `strtok` as `csstrtok`. Newlib keeps the save pointer in reent state. |
| `rint` | `fast_ftol`, `real_argb_color_to_pixel32`, `real_a_rgb_color_to_pixel32` | `fast_ftol` stores `(long)__builtin_rint((double)value)` and comments that the Xbox path is `FISTP` under the default control word (`source/cseries/cseries.h:335-343`). Pixel conversion uses the same builtin (`source/bitmaps/bitmaps_inlines.h:69-73`). The result follows the EE rounding mode. `_control87` is still pending. |
| `rand` | `get_number_suitable_for_initializing_random_seed` | The only rooted caller mixes `rand()` into the local seed (`source/math/random_math.c:156-159`). Newlib `libc_a-rand.o` advances a global sequence. That sequence is not proven against CE. |
| `towlower` | `csstrcasecmp` | `csstrcasecmp` folds each byte with `towlower` (`source/cseries/cseries.c:608-634`). Newlib `libc_a-towlower.o` is locale `wchar_t` conversion, not the ASCII identifier fold already approved for `_stricmp`. |

## Regression

`tests/test_hcu_external_review.py::test_toolchain_remainder_records_provider_and_caller_contracts` locks the wrapper, the wide-format drop, the unsized `vswprintf` call, the halt `exit(0)`, and the pending caller contracts above.
