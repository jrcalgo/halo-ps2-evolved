# M0 pinned Newlib string API review

## Scope and source identity

This batch reviews only the rooted, stateless Newlib string operations `strchr`, `strcmp`, `strcpy`, `strlen`, `strncat`, `strncmp`, `strncpy`, `strrchr`, `strstr`, `wcscmp`, `wcslen`, and `wcsncpy`. The source is the exact PS2 EE Newlib 4.6.0 pin `8881dc4b138f0561596980ac9a481c7e638aebd0` in [`toolchain-sources.json`](../config/toolchain-sources.json#L19). The current rooted R5900 link map selects each function from its corresponding `libc.a(libc_a-<name>.o)` archive member. These are not parent-generated empty functions.

## Semantics and CE callers

The narrow functions are standard C byte-string search, lexical comparison, copy, length, bounded concatenation, bounded comparison, bounded copy, reverse search, and substring search. Their callers include CE cseries path/string helpers, console completion, AI/HS parsing, file path handling, and error/debug output. Newlib's bounded operations retain standard semantics: `strncat` appends at most `n` source bytes then terminates; `strncmp` compares at most `n`; `strncpy` pads with zero bytes if the source is shorter and does not promise termination if the source reaches `n`. The caller must provide valid input/output spans; these APIs do not make arbitrary CE pointers safe.

The wide functions use 16-bit `wchar_t` under the PS2 prefix, matching the accepted HCU ILP32 ABI. `wcscmp`, `wcslen`, and `wcsncpy` therefore operate on CE wide-code units rather than 32-bit host wchar values. Callers are in CE Unicode string compare, formatting, and copy helpers. Stateful `strtok`, ctype/locale routines (`_ctype_`, `isalpha`, `isspace`, `tolower`, `towlower`), and formatting functions are deliberately excluded from this batch because they depend on additional global reentrancy/locale or formatting contracts.

## Disposition and evidence limits

Each approved ledger row names the pinned Newlib owner, exact implementation object, caller source hashes, and this report. `test_pinned_newlib_string_helpers_resolve_to_exact_archive_members` asserts the 12 exact archive-member resolutions and their ledger evidence. The tests establish selected provider identity, not a full target-side edge-vector suite for every routine; later toolchain qualification should add EE vectors for empty strings, NUL search, signed-char/high-byte comparisons, zero bounds, truncation/padding, and UTF-16 code units. No approval is made for `memcpy`: its many live callers require the separate overlap/bounds audit already documented. `strtok` remains pending because its state is tied to Newlib's reentrancy pointer; locale and formatted-I/O functions likewise remain pending.
