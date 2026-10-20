# M0 rooted `tolower` ASCII call-domain review

The only rooted `tolower` call sites are in
`source/main/console.c::console_tab_complete`. That routine enumerates
HaloScript names with `hs_tokens_enumerate` and compares the returned symbol
strings to determine a common ASCII prefix. These tokens are CE script/global
identifiers, not arbitrary player text or localized UTF-8. The console
completion loop therefore supplies values from the ASCII identifier alphabet
to the pinned Newlib C-locale `tolower` implementation.

The implementation resolves to `libc.a(libc_a-tolower.o)` and uses the actual
pinned `_ctype_` table. It folds ASCII upper case and leaves ASCII lower case,
digits, punctuation, and the terminator unchanged. Disposition is `implemented`
for this call domain only. This review does not bless signed negative `char`
values, arbitrary byte strings, Unicode case mapping, or `towlower`; the latter
remains pending its separate CE UTF-16/locale review.

`test_pinned_newlib_tolower_has_only_ascii_hs_completion_callers` locks the
sole source caller, exact archive member, existing table owner, and the fact
that `towlower` remains pending.
