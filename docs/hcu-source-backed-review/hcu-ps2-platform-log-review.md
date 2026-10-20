# M0 rooted `platform_log` diagnostic-only review

The exact rooted callers are `data_usable`, `game_state_check_data_arrays`,
and `lights_port_recover`. In each case the log is emitted after/beside the
caller’s state decision, not used as a result channel:

- `data_usable` records the invalid array once, emits the diagnostic, then
  returns `FALSE` either way.
- `game_state_check_data_arrays` emits a corruption explanation and then calls
  CE `error(...)`; the fatal/visible error handling is not inside
  `platform_log`.
- `lights_port_recover` repairs the out-of-order light state and clears its
  attachment indices before emitting the message, then returns `TRUE`.

The PS2 generated body is empty, so these messages are not retained in a
platform log. For the three exact rooted callers this is an observability loss,
not a change in successful simulation/resource state or failure control flow.
The symbol is approved `excluded-proven` only for those diagnostic calls; this
does not approve `error`, CE corruption detection, or the recovery routines as
no-ops. The caller ordering and return behavior are locked by
`test_platform_log_only_emits_diagnostics_after_caller_state_decisions`.
