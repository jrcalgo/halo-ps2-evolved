# M0 rooted stack-walk diagnostic review

The three rooted calls form one diagnostic-only family. `errors_initialize`
and `errors_dispose` call `stack_walk_initialize`/`stack_walk_dispose` to load
and release the desktop executable's debug-symbol table. The PS2 generated
bodies are both empty; consequently no table allocation is made and the paired
no-op disposal cannot leak that table. `stack_walk` enumerates frame addresses
and optionally symbol names for error output.

The CE `cseries_match_assert` macro calls `stack_walk(0)` only after its
assertion has failed, then independently calls `error(...)` and
`system_exit(-1)`. The fatal branch of `display_assert` similarly calls the
walker before writing the error. Successful calls to the memory/string helpers
do not call it. Thus the PS2 omission removes desktop stack-trace detail but
does not suppress the error report, change whether the assertion is fatal, or
affect successful simulation. The PS2 logger is the retained diagnostic owner.

The three symbols are approved as `excluded-proven` for frame/symbol
enumeration only. This is not approval to stub `error`, `system_exit`,
assertion behavior, or the CE error lifecycle. The focused source regression is
`test_stack_walk_is_diagnostic_only_and_does_not_replace_error_control_flow`.
