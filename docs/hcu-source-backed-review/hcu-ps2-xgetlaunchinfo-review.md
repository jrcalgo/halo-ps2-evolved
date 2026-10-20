# M0 rooted `XGetLaunchInfo` local-startup review

The only rooted caller is `shell_platform_initialize` in
`source/shell/shell_xbox.c`. It examines launch type/data only inside the
condition `!XGetLaunchInfo(...) && launch_data_type == LDT_TITLE`; nonzero is
the Win32/XDK failure result. On the PS2, no Xbox launch payload exists, and
`port/ps2/src/ps2_edge.c` returns that failure value. Short-circuit evaluation
therefore prevents reads of the intentionally untouched output objects.
`shell_platform_initialize` then returns `TRUE`, selecting ordinary local
startup rather than the optional XDEMOS launch path.

This justifies the current adapter for M1 local boot only. It does not emulate
Xbox title launch metadata, XDEMOS, resume/title launch, or any future PS2
launcher protocol. If such a launcher is added, it needs an explicit PS2-owned
launch-data contract and a new review rather than changing this result
implicitly. The focused contract check is
`test_xgetlaunchinfo_failure_selects_normal_local_shell_boot`.
