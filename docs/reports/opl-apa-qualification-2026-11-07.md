# OPL APA qualification — in progress

Physical PS2 compatibility is **not qualified**. The historical USB failure's
cause is unknown. No hardware launch, APA installation, menu-to-guest run, or
console gameplay observation has been obtained in this investigation.

## Frozen candidates

`build/opl-qualification/baseline/baseline.json` records file extents, SHA-256
hashes of all 68 files in each image, and 14 extracted ELFs per image (menu plus
13 guests). ISO copies are read-only. Existing user artifacts were not modified.

| Candidate | SHA-256 | Identity limitation |
|---|---|---|
| `build/c3/perf-fix-20261106/HALO_PS2_v4.iso` | `b49a1b1cac90dabb062e486299b8beaf15d41657e8843d09924d449431540870` | Latest dated candidate found; user has not identified it as stable |
| `build/c3/render-profile-gif-fix/HALO_PS2.iso` | `19879ed6adfa6bcdda59af3358e33310bacb92ecefcf4dea0a2e00718fd1c6c2` | October 31 candidate; not identified as the failed hardware image |

Tracked parent/dependency archives and binary dirty diffs are retained beside
the manifest. `working-parent/` also preserves current src/tools/config/tests,
including untracked implementation files. These are investigation-time sources,
not proof of which sources built either historical ISO. Existing ISO build
flags and original linked-library identities remain unknown.

The installed SDK resolves through
`build/c3/weapon-visibility-current-fresh/source-freeze/native-switch-r3/build/toolchain/install/ps2sdk`.
The manifest hashes the resolved current SDK archives, IRXs, linkfile, compiler,
and compiler-resolved CRT. Checked-out SDK source identity must not be substituted
for those actual binaries. New probe manifests also record source/SDK input hashes,
commands, link-map hashes, ELF hashes and packaged-image hashes.

## Source findings and changes

| Contract / evidence | Observed locally | Reproducer / corrective change | Verification / limit |
|---|---|---|---|
| SDK `ee/kernel/src/sifrpc.c`, `sceSifBindRpc` returns one bind reply; `sceSifCheckStatRpc` tracks outstanding ownership | Halo submitted one NOWAIT bind then polled `server` without rebinding after a negative reply | Retry completed negative replies; never overwrite a still-pending static client | Host fixture covers delayed registration, outstanding request, missing server, module failures; historical causality unproven |
| Exact OPL 1996 `src/system.c:LaunchLoaderElf` builds `cdrom0:\\<startup>;1` for its game loader, regardless of backing device | Existing `opl-hdd` means `pfs0:/` standalone files | Added explicit `opl-iso` profile selecting `cdrom:/`; retained standalone profiles | Profile tests pass; hardware virtual-disc reads pending |
| `src/system.c` passes PS2LOGO and game ELF separately; `ee_core/src/main.c` / `syshook.c` subsequently load game | PS2 logo does not establish Halo entry | Numbered diagnostic stages and production-CRT entry trampoline | Entry and packaged-disc probes pass PCSX2; OPL hardware pending |
| `ee_core/src/modmgr.c:LoadElf` delegates ELF loading to IOP loadfile RPC and receives EPC/GP | Full game segment loading is not performed by the GUI's embedded-EE-core copy loop | Keep installed production CRT; trampoline preserves arguments, uses only k0/k1 and GS BGCOLOR before jumping to `__start` | Probe compile/link and PCSX2 entry pass; all production ELF placement audits pending |
| OPL `include/iosupport.h`: default module storage `0x00097000`; `src/system.c` computes dynamic end | Actual storage end depends on loader binary, modules and settings | Keep Halo's EE reserve intact; do not infer non-overlap from default start alone | Exact running loader binary/module extent still needed |
| Halo `hcu_chain_to_gameplay` resets IOP then calls `LoadExecPS2`; OPL `syshook.c:sysLoadElf` resets/reinjects services itself | Explicit reset and unbounded sync precede handoff; no quiescence proof | Instrumented handoff and returned-load error; lifecycle behavior left unchanged pending reproducer | Not corrected or qualified |
| Halo pad startup loads `rom0:XSIO2MAN`, `XMTAPMAN`, `XPADMAN` before storage | ROM availability and service protocol are unverified on this console | Diagnostic stage before controller initialization; visible failure code | No model-specific module replacement inferred without evidence |

The separate exact source archive is
`build/opl-qualification/reference/opl-1996.tar.gz`, commit
`b6717a842e02a8010abaf23a9116081ec43d8512`, from
[Grimdoomer's build 1996 release line](https://github.com/grimdoomer/Open-PS2-Loader/releases/tag/v1.2.0.6-1996-Beta).
The upstream OPL submodule remains unchanged. Its locally available `0.9.3`
tag was separately archived; DB commit `1922f1ee78a` was not present in that
object database. No actual user OPL ELF hashes have been supplied.

[Butterscotch's startup source](https://github.com/ButterscotchRunner/Butterscotch/blob/main/src/ps2/main.c)
embeds controller and memory-card modules. That is a useful candidate strategy
if ROM service availability proves faulty; it is not proof of Halo compatibility.
[Quake II's boot implementation](https://github.com/glampert/quake2-ps2/blob/master/src/ps2/system/iop_boot.cpp)
tracks module identities/versions and IOP memory, but its default reset policy
must not be copied blindly into Halo's OPL virtual-disc environment.
[OSD initialization guidance](https://github.com/ps2homebrew/OSD-Initialization-Libraries)
is a model-specific comparison reference; this console's ROM remains unknown.

## Diagnostic artifacts

Rebuild with `python3 tools/build_opl_boot_probes.py`. Outputs and exact hashes
are in `build/opl-qualification/probes.json`.

1. `probe-1/HALO_DIAG_1.iso`: register-only CRT entry colour, libc marker,
   minimal GS screen and main marker. No controller or storage initialization.
2. `probe-2/HALO_DIAG_2.iso`: EE allocation, SIF/loadfile, named module IDs.
   These IDs do **not** establish exported-service protocol compatibility.
3. `probe-3/HALO_DIAG_3.iso`: production storage initialization and file reader,
   `cdrom:/PROBE.BIN`, complete SHA-256 comparison, aligned/unaligned sector
   crossings, repeated open, final short chunk, prefetch then close/settle.
   The 16,421-byte payload's SHA-256 is
   `a3f8ab90030145c5012a5512d87dd1878b4a2e1bd05c05556613b0fc0a8fee37`.

The probes use the production publisher's xorriso flags, boot filename, logo
publisher and sector-257 path-table publisher. They contain a small payload,
not production-sized memory or DVD layout, so they cannot qualify those layouts.
The builder checks embedded bytes against the inputs. Independent OPL parser
and real-console path-table acceptance are still pending.

`WORLD_HCU_BOOT_DIAG=1` in `tools/ee-world.mk` enables optional full-machine
hooks. Use a fresh output directory, the installed production CRT and current
memory ledger. The entry trampoline changes the ELF entry address only in this
diagnostic build. The libc wrapper records entry/completion. Display/exception
code is absent when disabled. Stages 2–12 name libc, main, allocation, SIF,
controllers, FileXio, disc read, menu, handoff, gameplay entry and first frame.
SIF/disc stages currently execute in the small probes; full-machine hooks cover
main, allocation, controllers, FileXio, menu, handoff, guest and frame boundaries.
After the renderer owns GS, stage progress uses BGCOLOR rather than resetting
its display. A production overlay and first-disc-read hook remain unfinished.

The diagnostic exception path uses EEDEBUG and the SDK GS text screen, reports
stage/result/cause/EPC/bad address, and uses no file or network operations.
It still depends on working CPU/GS and the SDK's polling GIF implementation;
it is not a proof against corrupted stacks or wedged GS/DMA. No trace ring or
heap allocation is added; static bytes are charged through the existing NOBITS
ledger. Full diagnostic linked-image placement must pass before hardware use.

No new production release image or 13-guest rebuild is claimed. The three
probes and full-machine main/menu source objects compile successfully. The
production handoff and resource/renderer audits remain open.

## Local verification

22 focused host tests pass across storage boot, asset profiles, file reader,
menu/render profiles, physical evidence parsing, and baseline extraction.
The expanded parent-link suite produced 33 passes and two failures: an existing
hard-coded file-budget expectation and a missing
`build/m2-c2-resume-budget-v3/result-partition-sidewinder_marine_shotgun_4p4bot.json`.
The parent-link change only adds the `opl-iso` profile; memory calculations and
these fixtures were not changed.

PCSX2 recompiler runs reached the small-probe success markers with host access
disabled: direct ELF probe 1, disc boot probe 1, and disc boot probe 3. Retained
logs/results are under `build/opl-qualification/emulator*.log` and their linked
run directories. Use the exact hashes in each result; rebuilding ISOs changes
publisher timestamps. These observations establish small-probe behavior only,
not menu/gameplay or physical OPL compatibility. No sustained-FPS claim is made.

## Physical handoff and outstanding acceptance

The user confirmed a direct Ethernet cable and PS2 launcher/OPL screen. Host
`enp4s0` has carrier but no IPv4 address. Wi-Fi owns `192.168.1.224/24` and the
default route. The temporary setup command needs the user's sudo password:

```
sudo ip address add 192.168.0.1/24 dev enp4s0
```

`build/opl-qualification/PS2LINK_USB/` contains a newly built, unpacked
`PS2LINK.ELF` and adjacent `IPCONFIG.DAT` selecting
`192.168.0.10 255.255.255.0 192.168.0.1`. Copy the folder to a FAT32 USB stick
and launch the ELF using wLaunchELF/uLaunchELF FileBrowser (`mass:`). Its modules
are embedded. Leave its Ready screen visible. This follows the repository's
`submodules/ps2link/README.md`. PS2Link resets/changes the IOP; its runs are
supplementary and do not replace OPL APA acceptance.

Next required evidence: console SCPH/ROM/region, adapter/HDD/APA installer,
actual OPL ELF hashes and settings, baseline/historical image confirmation,
network readiness, and photographs/video of each physical probe. Install only
dedicated diagnostic game slots with unique titles on the existing APA drive;
no drive formatting or changes to existing games have been performed.

All physical acceptance remains pending: 10 cold plus 5 warm OPL 1996 APA
launches, real menu-to-guest launches for all 13 maps, controls/sound/settings
and card-absent startup, four graphics profiles, one-/two-player layouts,
20-minute Blood Gulch sessions for both player counts, exit/reload/relaunch,
USB reproduction, older loader comparisons, and final production image without
network/diagnostics. OPL APA emulation, full memory/DMA/service audit, pending-RPC
failure testing on hardware, and measured performance also remain open.

### PS2Link hardware follow-up

The user launched the locally built `PS2LINK_USB/PS2LINK.ELF` and reported a
black screen. No PS2Link text has been confirmed. The PC now has
`192.168.0.1/24` on `enp4s0`; two pings to `192.168.0.10` received no replies.
This is a PS2Link launch failure observation, not a Halo/OPL APA run.

The local ELF (`7f60b4442c5ab3c0a3d7557e0405da8759f78a9ed74aab78ed92b089503efcd8`)
is unpacked, has entry `0x00094a70` and loads at `0x00094000`. Its LOAD end is
`0x000ded60`, below its configured stack base `0x000f8000`; no overlap was
found in that static check. The official packaged v1.9.1 release (GitHub's
`RenameMe` tag, commit `0269a955`) has entry `0x01d0001c`, and LOAD at
`0x01ced160`. Different launcher handling of these layouts is a hypothesis,
not a confirmed cause.

A replacement official package is staged in
`build/opl-qualification/PS2LINK_OFFICIAL/`, with the same direct-PC IPCONFIG.
Official download URL:
`https://github.com/ps2dev/ps2link/releases/download/RenameMe/ps2link-0269a955-default.tar.gz`.
Archive SHA-256:
`229715fa199ac16b3fe493d849759157878d70720cc18fb0e4f548024a70a4af`.
Official ELF SHA-256:
`dec2244c477e4e0e15e2ae451bd16e6ecf901e84d16673a2a1642326d6b89440`.
Hardware outcome for this replacement is pending. The failed local file remains
preserved. No claim that it was hardware-tested should be inferred from the
earlier successful compilation or from the separate Halo probe emulator tests.

### Physical PS2Link probe results

The user supplied displayed IP `192.168.1.10`; the official release did not use
the adjacent `192.168.0.10` config as expected. The PC now also has
`192.168.1.2/32` on `enp4s0`, with a specific route for `192.168.1.10/32` over
that interface. Wi-Fi retains the subnet/default route. Two pings succeeded
(0.600 and 0.312 ms).

Probe 1 ELF SHA-256
`024e5ec6e848146270eac65b36ce22eef4e42442fa466c95997c6284663850b9`
loaded via PS2Link, emitted `HALO_OPL_PROBE complete level=1`, and the user
confirmed HALO DIAGNOSTIC, PROBE 1 and PROBE COMPLETE all visible.
Probe 2 subsequently emitted its level-2 completion marker and the user
confirmed all screen text visible. Its exact identity/log are retained in
`build/opl-qualification/hardware/probe-2-ps2link.json`.

PS2Link refuses another EXECEE while the preceding probe holds its user thread.
The first Probe 2 command therefore did not load anything. A network PS2Link
reset released Probe 1; the subsequent Probe 2 command succeeded. Future probes
require a reset or a fresh launcher session between runs.

These are physical CPU/CRT/display and EE/SIF-inventory observations in the
PS2Link environment. They do not qualify OPL startup, virtual-disc access,
full production memory placement or gameplay. Module IDs are currently only
on-screen; their values/versions and console SCPH/ROM remain unrecorded.
An optional OPL USB comparison kit is prepared in
`build/opl-qualification/OPL_USB/`, with three diagnostic images under DVD.
No OPL/APA probe has yet run and no HDD installation has been changed.

### Ethernet APA installation preparation

The user normally connects the HDD to a PC installer and explicitly authorized
Ethernet/HDL Dump installation for these tests. SCPH identification is deferred
at the user's request. Exact build-1996 source documents NBD replacing the old
HDL server; the menu shows Start NBD Server only when HDD startup and write
operations are enabled. The user was directed to configure static
`192.168.1.10/24`, gateway `192.168.1.2`, and start that server in OPL.

The official HDL Dump client was built from commit
`32c296c69cf9c263fcbe035004aa28c345b3b279`; identities are retained in
`build/opl-qualification/hdl-dump-client.json`. A local configuration-path
patch accepts `HDL_DUMP_CONFIG`, keeping the client config inside this workspace
without changing HOME or any disk algorithms. Linux's `nbd-client` and kernel
NBD setup require user sudo authentication. The requested target is `/dev/nbd0`,
which did not exist before setup; no existing NBD connection was found.
A temporary per-user ACL will let the agent use this device after connection.
Before any installation, read and retain APA/game TOCs and backup TOC, verify
APA and free space, check unique diagnostic names, then install only those new
slots. Read back each new ISO and compare hashes before launch. No disk has yet
been accessed or written during this preparation.

Installer preflight found an actual ISO metadata incompatibility:
the existing xorriso command left the PVD system identifier blank. HDL Dump's
`isofs_get_ps2_cdvd_info` requires `PLAYSTATION` and rejected the original small
probe ISO as not a PlayStation disc. Added `-sysid PLAYSTATION` to both production
and probe publisher commands. Fresh images are separately retained under
`build/opl-qualification/apa-probes/`; previously hardware-/emulator-tested
artifacts were not overwritten. All three fresh images pass the independent
HDL Dump `cdvd_info` parser with startup `HPS2_000.01`, volume `HALO_PS2`.
This corrects installer recognition; it is not evidence for the cause of the
historical OPL black screen. Eleven focused tests pass after this publisher
change. Hardware OPL launch and a production ISO rebuild remain pending.

### APA installation completed and verified

The user installed/connected nbd-client and granted the scoped device ACL.
The device is 488,397,168 sectors of 512 bytes (250,059,350,016 bytes), reported
as 232.9 GiB by lsblk. It was unmounted and valid APA. The original TOC contained
88 main partition entries, with 3,200 MB free by HDL Dump's accounting.
A full interval-based APA metadata backup completed successfully and was checked
for expected size (3,817,472 bytes) and APA signature, then marked read-only:
`build/opl-qualification/hardware/apa-toc-backup.bin`.

Installed exactly three new 128 MB diagnostic slots over OPL NBD:

| Title | APA partition | Installed ISO SHA-256, verified by extraction |
|---|---|---|
| Halo APA Probe 1 | `PP.HPSX-00001..HALO_APA_PROBE_1` | `fd28cd7002e0bad2a1eea9294245b52e101b0d02b94c1aa1d44025e58fe363fb` |
| Halo APA Probe 2 | `PP.HPSX-00001..HALO_APA_PROBE_2` | `5a937134c2a570abd1a150b642119a436de23572889b8e8d8295c13694e24717` |
| Halo APA Probe 3 | `PP.HPSX-00001..HALO_APA_PROBE_3` | `c002c4ad896db451115c54a3598fc7757377f198c0bc6e1e70a8739e412a11dc` |

Post-install TOC has 91 entries and 2,816 MB free. All 88 original TOC lines
(type, start, partition count, size and ID) are unchanged; exactly the above
three entries were added. This verifies the partition entries, not full hashes
of every pre-existing game. All three installed ISOs were extracted after an
fsync/cache-discard request, and their SHA-256 hashes match the source images.
Logs, backup hash, exact source/readback identities and metadata comparison are
in `build/opl-qualification/hardware/apa-installation.json` and
`verification-by-partition.log`.

Readback initially exposed an upstream HDL Dump title-lookup bug unrelated to
installation: `hdl_ginfo_read` calls strcpy into a 65-byte game-name field while
reading the existing longer title `Tom Clancy's Ghost Recon - Advanced Warfighter
(Europe) (En Fr De Es It)`. The debugger caught glibc's checked-copy abort in
that call. No additional game writes were made to resolve this. Readback used
the exact new APA partition IDs, bypassing the global game-title lookup, and all
three extracts succeeded. Debug trace is retained in `readback-debug.log`.

The host device is accessible only outside the sandbox's filtered /dev view;
read/write tools were run through approved escalations. The user must disconnect
with `sudo nbd-client -d /dev/nbd0`, then can dismiss OPL's NBD screen and launch
Halo APA Probe 1 with baseline per-game settings. OPL boot outcomes remain
pending; installation/readback success does not establish executable entry.

### First OPL APA launch observed

The user reports **Probe 1 complete** after launching the installed diagnostic
from OPL's internal-HDD game list. This establishes the small probe's entry,
CRT/libc/main and diagnostic display under the physical APA launch route.
The ISO identity and exact partition are retained in
`build/opl-qualification/hardware/probe-1-opl-apa.json`.
This is one reported launch, not the repeated-launch acceptance gate. Actual
OPL ELF hash, console SCPH/ROM, cold/warm classification and visual capture are
still unrecorded. No virtual-disc read, full Halo menu, chained guest or gameplay
claim follows from this probe. The user was directed to launch Probe 2 next.

### Second OPL APA probe observed

The user reports **Probe 2 complete** from the installed HDD diagnostic.
This establishes small-probe EE allocation and SIF/loadfile/module inventory
completion on the physical APA route. The exact installed image is recorded in
`build/opl-qualification/hardware/probe-2-opl-apa.json`. Individual module ID
values/export versions are not yet captured. This does not establish FileXio
binding or asset access. Probe 3 is the next virtual-disc read/hash gate.

### Third OPL APA probe and production-layout menu preparation

The user reports **Probe 3 complete** in response to the explicit checksum,
range/reopen/prefetch-close completion criteria. Its exact installed ISO is
recorded in `hardware/probe-3-opl-apa.json`. This establishes the small probe's
FileXio binding, virtual-disc reads, SHA-256 comparison, sector crossings and
prefetch-close completion on the physical APA route. It does not establish full
production allocation, controllers, menu or map handoff.

A separate full-machine diagnostic menu was compiled using the quiet C3 menu
profile, current production CRT and installed libraries. The new
`--boot-diagnostics` option in `hcu_parent_link_probe.py` passes the diagnostic
flag through compilation and the manual final link, including the entry
trampoline, libc wrapper and EEDEBUG library. Runtime failures before menu hold
the diagnostic screen. The optional instrumentation does not alter release
behavior. Current source/diffs are frozen in
`build/opl-qualification/menu-diagnostic/source-freeze/`; the link report records
exact object, linked closure, ELF and map identities.

The host placement helper still hard-coded the pre-growth arena total
24,117,248 bytes. It now derives the carved total from the current budget
(26,738,688 bytes), checked against the engine header. Outdated boundary fixtures
were updated to derive their synthetic overages from that same current budget.
The existing fixture-dependent test requiring the absent historical Sidewinder
report remains excluded; 37 focused tests pass with one such test deselected.
No EE reserve capacity was changed.

The diagnostic runtime ELF has debug sections stripped to fit the original
menu file slot. All PT_LOAD contents and the entry address were verified
identical to the unstripped linked image. Runtime ELF SHA-256:
`e9516b3fd80a1c79cd77ec986f92027d25fbec95eb411aa0f0b0bc6a064bf75e`.
`tools/build_opl_menu_diagnostic_iso.py` cloned the frozen v4 ISO, replaced only
the menu within its existing extent (LBA 545), and set the PVD system identifier
to PLAYSTATION. All other 67 files, including all 13 gameplay ELFs, and every
other file extent/hash were checked unchanged. Original ISO size is retained:
1,729,507,328 bytes. The initial attempt inherited the frozen file's read-only
mode and stopped before modification; the builder now makes only its new copy
writable, and the successful image uses a fresh filename.

Prepared image: `build/opl-qualification/menu-diagnostic/HALO_MENU_DIAG_R1.iso`.
SHA-256: `4236ad564faff34148aa98b9cd93407537625c05bc22b50bcf2fb23c183fd960`.
This is a diagnostic menu with frozen comparison guests, not a rebuilt release.

The exact packaged runtime ELF reached the first menu frame in PCSX2 with
HostFs=false and EnableFastBoot=false (full BIOS disc startup), remained stable
for the requested three seconds, and passed linked/runtime physical-placement
checks. Runtime reserve start was `0x01cf0000` and headroom was 184,550 bytes.
Results: `menu-diagnostic/emulator-full-bios-r1.log` and its linked run directory.
The runner now enforces requested physical evidence for every stage, can find
isolated link reports alongside their ELF, and retains an explicitly supplied
ELF identity during disc boot when physical qualification is required. Earlier
main-menu runs set the require flag without enforcing it at that stage; this
new full-BIOS run supersedes them for placement evidence.

The user restarted OPL's NBD server, reconnected the PC, and approved installation
into one further dedicated APA diagnostic slot. `Halo Menu Diag` is being written
from the verified image above. The live `hdl_dump inject_dvd` transfer log is
`build/opl-qualification/hardware/install-menu-r1.log`; at the latest check it
had reached 22% at about 0.65 MB/s with roughly 31 minutes remaining. No disk
write or verification claim is made until the transfer returns, the APA TOC is
checked, and the installed partition is extracted and hashed. Physical full-menu
startup remains pending.

### Next-stage Blood Gulch diagnostic sizing

A compact fatal-only EE exception handler was prepared for the next guest build.
It registers SDK VTLB/common vectors, switches to an 8 KiB dedicated stack, and
captures Cause/EPC/BadVAddr before calling the GS error display. This removes the
interactive EEDEBUG stacks and frames from that diagnostic ELF. The isolated
Blood Gulch guest links with no undefined symbols, but its PT_LOAD file size is
2,558,596 bytes against the fixed 2,555,904-byte cap (2,692 bytes over). It is
not accepted or queued for installation. The deployed full-menu R1 still uses
the previously built and PCSX2-verified EEDEBUG handler; the compact variant has
not yet received an exception runtime test.

### Full-menu APA installation integrity

`Halo Menu Diag` installed successfully as `PP.HPSX-00001..HALO_MENU_DIAG`.
The APA inventory contains 92 entries: all 91 pre-existing entries are unchanged
and exactly one new 1,664 MB slot was added. Free space is 1,152 MB. The full
1,729,507,328-byte partition was extracted and its SHA-256 matches the source
ISO exactly (`4236ad564faff34148aa98b9cd93407537625c05bc22b50bcf2fb23c183fd960`).
The installed image is ready for the physical OPL 1996 APA menu-startup check;
that launch has not yet been observed.

### Full menu hardware failure and CRT ladder

The user reports a persistent black (technically red) screen on all three OPL
versions available on the console. No menu text appeared. The exact OPL binary
hashes and visual capture are still absent. The R1 trampoline explicitly writes
BGCOLOR=0x40 (dark red) at ELF entry; its next marker is yellow at the libc
wrapper. Dark red is therefore consistent with execution entering Halo and
stalling during earlier CRT work. This is a narrowed hypothesis based on the
reported color, not a confirmed failing instruction.

A separate 4,192,256-byte ISO retains the full menu code/BSS layout and deliberately
omits assets to test startup without another full-disc transfer. Linker wrappers
mark SetupHeap entry/return (green/cyan), _InitSys entry/return (blue/magenta),
argument/cwd parsing entry/return (orange/white), followed by yellow at libc init.
The guest PT_LOAD file size is 2,365,316 bytes and necessary placement checks pass.
All four CRT wrapper call sites were verified in the linked disassembly.
Artifact: `build/opl-qualification/crt-ladder/HALO_CRT_LADDER.iso`, SHA-256
`8dc810b2e25e2f1714ce84eb8cc0bc8fe1ed595e94d07c6120b15db140eb42b0`.
This probe does not qualify menu assets or gameplay.
The CRT ladder ISO passed PCSX2 full BIOS disc startup with HostFs disabled,
reaching the runtime `memory-physical` marker and passing linked/runtime placement
checks. The runner's stage label is `main-menu`, but its explicit success marker
is memory initialization only; this result makes no menu-presentation claim.

### CRT ladder APA installation

The first preflight was stopped while reading a stale NBD device with no live
TCP connection; no installation had started. After the user reconnected NBD,
the inventory matched all 92 previous entries and 1,152 MB free. `Halo CRT Ladder`
installed into a new 128 MB slot, leaving 1,024 MB free. All 92 original entries
remain unchanged, and a full extracted ISO SHA-256 matches
`8dc810b2e25e2f1714ce84eb8cc0bc8fe1ed595e94d07c6120b15db140eb42b0`.
The console launch and final visible CRT marker are pending.

### CRT ladder blue screen: kernel initialization isolated

The user reports a persistent blue screen from the CRT ladder. Blue is emitted
immediately before the real `_InitSys()` call, and its magenta return marker was
not observed. This places the observed stall after BSS clearing, SetupThread,
SetupHeap and the CRT cache flush, within SDK kernel initialization or a fault
there. It does not yet identify a particular kernel patch or establish a fix.

The exact linked `_InitSys` calls InitAlarm, _ps2sdk_init_timer, InitThread,
InitExecPS2 and InitTLBFunctions in that order. A new kernel ladder preserves all
five calls and adds bright red, green, cyan, yellow and white entry markers
respectively. Linked disassembly verifies all five wrapped targets. The small
ISO passed full BIOS PCSX2 startup with HostFs disabled and runtime placement
checks through the memory-physical marker. This is startup evidence only.
Kernel ladder ISO SHA-256:
`f85c091b1e15d7c6e3e000675764a4ee3f0bd3e11e1e540b6732bc8281ad2937`.
Hardware installation and observation remain pending.

### Kernel ladder APA installation verified

The live NBD preflight matched all 93 prior entries with 1,024 MB free. The
kernel ladder installed in one new 128 MB slot. APA shortened its partition ID
to `PP.HPSX-00001..HALO_KERNEL_LADD`; the initial verification assertion expected
the full name and stopped after installation. Verification resumed read-only
using the actual ID, with no repeated installation. All 93 prior entries are
unchanged, and full readback SHA-256 matches
`f85c091b1e15d7c6e3e000675764a4ee3f0bd3e11e1e540b6732bc8281ad2937`.
The console title is `Halo Kernel Ladder`. Hardware marker observation is pending.

### Teal kernel marker and ABI collision found

The user reports teal/aquamarine from the kernel ladder, matching the marker
before InitThread. Alarm and timer initialization returned. Disassembly of the
actual linked InitThread shows its one-argument PS2 CreateThread call targeting
the CE Xbox facade at 0x0010bb8c. That facade uses a six-argument Xbox ABI and
conditionally writes through its sixth argument register, which the SDK caller
does not initialize. Thus the linked startup has a confirmed ABI violation;
the exact hardware fault/write location is still unknown.

Comparing CE platform exports with the installed libkernel archive found two
collisions: CreateThread in ps2_edge.o and ResumeThread in ps2_platform.o.
The CE PS2 forced prefix now maps these Xbox APIs to halo_xbox_CreateThread and
halo_xbox_ResumeThread. A fresh CE rebuild is underway. The parent linker now
rejects CE exports overlapping libkernel symbols; the new check correctly rejects
the preserved original ps2_edge.o for CreateThread. Hardware confirmation of the
fix remains pending. Original root/edge/platform objects and report were retained
under build/opl-qualification/pre-thread-fix-closure before rebuilding.

### Thread ABI fix built and emulator checked

The initial fresh link exposed that the generated facade emitter also needed
lookup aliases for the renamed XDK symbols. `hcu_ps2_link.emit` now looks up
the original XDK declarations for these two names; the forced PS2 prefix emits
the namespaced definitions. A fresh closure compile and facade rebuild then
linked successfully, and the joint linker collision guard passed.

In the corrected menu ELF, CreateThread at 0x0013c2e0 is the SDK's four-instruction
syscall-32 wrapper. The Xbox stub is separately exported as
halo_xbox_CreateThread at 0x0010bb8c; the generated ResumeThread facade exports
halo_xbox_ResumeThread. The new small ISO passed full BIOS PCSX2 startup with
HostFs disabled and linked/runtime placement checks through memory-physical.
This does not establish physical hardware progress past InitThread or menu/gameplay
compatibility. Source fix snapshots are retained in thread-fix/source-fix.

Prepared hardware image: build/opl-qualification/thread-fix/HALO_THREAD_FIX.iso
SHA-256: `5f18e3b163e87c6fdc7eb931f68be867c2f9509c5dd8c2bd1b910a75834f1cf4`.

### Corrected thread-startup probe installed

The NBD preflight matched all 94 prior APA entries and 896 MB free. `Halo Thread
Fix` installed in one new 128 MB slot (`PP.HPSX-00001..HALO_THREAD_FIX`), leaving
768 MB free. All 94 prior entries are unchanged. Full extracted-image SHA-256
matches `5f18e3b163e87c6fdc7eb931f68be867c2f9509c5dd8c2bd1b910a75834f1cf4`.
The physical launch result is pending. The image omits assets intentionally;
progress beyond kernel startup is the next qualification gate.

### Corrected startup reached stage 8 on physical console

The user reports teal followed by `HALO BOOT FAILED / STAGE 8 ERROR -1` from
Halo Thread Fix. This demonstrates progress through SDK kernel initialization,
libc/main, EE allocation and controller/FileXio initialization after the thread
namespace fix. Stage 8's generic error does not independently identify its exact
failed operation; omitted UI assets are the expected failure in this image.

A new 41,127,936-byte menu-only ISO includes exact frozen baseline UI.MAP/UI.HP2,
loading image, menu textures and audio, with flat and directory aliases. It uses
the same corrected menu runtime ELF. Packaged root file hashes match inputs and
the root directory occupies one sector. The release-specific directory validator
requires all gameplay maps/guests and therefore is unsuitable for this menu-only
probe; the root-sector limit was checked directly instead.

The image passed full BIOS PCSX2 startup with HostFs disabled, reached the actual
main-menu-frame presented marker, and stayed stable for three seconds with
linked/runtime physical placement checks. This supersedes memory-marker-only
emulator evidence for menu startup. It contains no chained gameplay guests.
Image: build/opl-qualification/menu-assets-check/HALO_MENU_ASSETS.iso
SHA-256: `c2bc5489149a2db3ff4608e1404311c35075f32069a6d148fce664165ec72b60`.
Physical installation/menu observation remains pending.

### Menu asset probe installed and verified

`Halo Menu Assets` installed as `PP.HPSX-00001..HALO_MENU_ASSETS` in a new 128 MB
APA slot. The preflight matched all 95 prior entries; post-install comparison
confirms those entries unchanged and exactly one added slot. Free space is
640 MB. Full 41,127,936-byte readback SHA-256 matches
`c2bc5489149a2db3ff4608e1404311c35075f32069a6d148fce664165ec72b60`.
The next console check is menu presentation, D-pad navigation and menu audio.
This image contains no gameplay guests, so map launch is not its acceptance gate.

### Menu asset probe also failed at stage 8

The user reports teal, brief unreadable text, then `HALO BOOT FAILED / STAGE 8
ERROR -1` from Halo Menu Assets. The menu did not appear. Stage 8 includes
renderer/snapshot storage binding and multiple asset/service operations, so
missing assets were not a confirmed explanation for the previous small probe.
The known CreateThread collision is corrected and startup progresses, but this
second failure remains unidentified.

Diagnostic failure calls now include `__FILE__` and `__LINE__`; the no-return GS
failure screen retains `SITE filename:line` beneath the stage/error. It still
uses no filesystem/network services. A new menu-site image contains the same
five frozen UI assets and the corrected thread ABI. Its source files are retained
under menu-site-assets/source so the reported source location remains resolvable.
ISO SHA-256: `70e5b5026e5e4331a38410bada881ca383088b319579475ca3ff3fff314dd5ff`.
Hardware installation remains pending.

### Rich held failure report implemented and visually checked

At the user's request, failure reporting now retains an explicit reason and
source file/line, diagnostic SP/GP, CP0 status/cause/EPC/BadVAddr, and a fixed
24-record trace. CP0 fields are explicitly marked as potentially preceding the
failed check. The trace retains stage transitions, EE boundaries, snapshot and
DMA allocation sizes/addresses, FileXio bind/module results, and UI file-probe
stat/open/read/seek/EOF context. No diagnostic screen filesystem/network calls
or dynamic allocations were added. The 384-byte ring plus counters resides in
NOBITS and is charged by the existing resident ledger; the EE reserve is intact.

Visual verification of an intentional missing-asset failure exposed vertical
clipping, then terminal wrap in the first two-column layout. The final layout
uses two columns of twelve records within the SDK's 80-column terminal, margins,
and a disabled cursor. Its held screen was captured and inspected at
menu-rich-failure/held-error.png. The normal acceptance runner correctly rejected
the intentional image's loading-screen-assets failure; a direct controlled run
was used to keep that expected failure visible for capture. Final normal-menu
ISO still passes full BIOS startup, HostFs=false, first menu presentation and
three seconds of observation with runtime placement checks.

The host storage-boot fixture passes. The file-bridge host fixture fails to link
because the SDK's non-TLS errno reference conflicts with host libc TLS errno;
the same failure was reproduced using the HEAD version of hcu_file_bridge.c.
No claim of a passing file-bridge host fixture is made.

Final rich image: menu-rich-assets/HALO_MENU_RICH.iso, SHA-256
`378c21f268f3c407d59d4a8ddd94c84ceeafff13da46cad306e0eec342a46dcf`.
Exact diagnostic sources are frozen in menu-rich-assets/source. Hardware
installation and identification of the current stage-8 failure remain pending.
The simpler menu-site image was superseded before installation.

### Rich installation preflight blocked before writes

After the user reported ready, TCP still showed the same NBD client port used
for the previous asset install. The bounded TOC preflight produced no output;
its hdl_dump child remained in uninterruptible folio_wait_bit_common on /dev/nbd0
after timeout requested termination. No install-rich.log was created and no
APA write started. The installer parent was stopped before reconnect. An attempt
to detach with sudo -n failed because a password is required. User-side NBD
disconnection/reconnection is needed to release the blocked read and resume.

### Rich diagnostic installation verified after reconnect

The reconnected NBD client used a new TCP session. Preflight matched all 96 prior
APA entries and 640 MB free. `Halo Menu Rich` installed as
`PP.HPSX-00001..HALO_MENU_RICH` in a new 128 MB slot; all 96 prior entries remain
unchanged, with 97 total entries and 512 MB free. Full extracted-image SHA-256
matches `378c21f268f3c407d59d4a8ddd94c84ceeafff13da46cad306e0eec342a46dcf`.
The source-location/reason/trace screen is now installed for the next physical
OPL launch. Current stage-8 failure identification remains pending.

### Rich trace identifies metadata validation; known-asset probe corrected

The user transcribed reason `maps/ui.map read-only file probe failed`, SITE
hcu_main.c:5115, and later the bottom trace label `validate-f`. This is the
validate-file branch: stat returned success but classified the path as a
directory or zero-length file, before attempting the main probe's descriptor
open/read. The CP0 values were retained as incidental state, not treated as
fault evidence.

Exact OPL 1996 source ioops.c:cdrom_getstat writes sceCdlFILE into iox_stat.attr
onward and leaves mode unwritten. The SDK fileXio_getstat_RPC copies an
uninitialized local iox_stat_t in full. This can deliver a stale directory mode
for a valid file. Zeroing the EE destination alone would not fix the IOP-sourced
mode. A regression models valid readable bytes/size with mode=directory and
reproduces the old validate-file failure.

Added a startup-specific hcu_file_bridge_probe_asset: it logs stat as advisory
and uses open/Lseek-derived nonzero size, first-byte read, seek-end/EOF, and close
to qualify a known packaged asset. Generic bridge probe/stat directory semantics
remain unchanged. No alternate backing device or filesystem is attempted. The
regression checks strict metadata rejection, successful known-file validation
with stale mode, missing-file rejection, read failure, closure and no allocations.
All three focused bridge/storage/reader tests pass. The bridge host fixture was
repaired to model target errno separately from host TLS errno and to provide its
missing loading-screen/libc-wrapper dependencies; libc fallback is asserted
unreachable in that fixture.

The corrected image passed PCSX2 full BIOS menu startup with HostFs disabled,
three seconds of menu observation, and linked/runtime memory placement checks.
Hardware confirmation is pending. Image: menu-stat-assets/HALO_MENU_STAT.iso
SHA-256: `5e3b94eda0577e504f756f3f80b7c4fdb640dea66189ac0b54fd8dcfb9e77ab5`.

### Known-asset metadata correction installed and verified

The new NBD session passed preflight against all 97 prior entries, with 512 MB
free. `Halo Menu Stat` installed as `PP.HPSX-00001..HALO_MENU_STAT` in a new
128 MB slot. Post-install comparison confirms every prior entry unchanged and
exactly one new slot, leaving 384 MB free (98 total entries). Full readback
SHA-256 matches `5e3b94eda0577e504f756f3f80b7c4fdb640dea66189ac0b54fd8dcfb9e77ab5`.
Physical confirmation of menu presentation/navigation/audio remains pending.

### Loading screen reached; startup watchdog prepared

The user reports that Halo Menu Stat renders the loading screen, with no visible
loading-bar progress and no menu. This establishes loading-image rendering, but
the screen begins before the UI read probe and does not by itself establish that
all subsequent file operations or a second loading frame completed.

Added a diagnostic-only startup watchdog with a static 8 KiB stack, charged to
resident NOBITS. A priority-zero EE thread samples every 100 ms and suspends the
main thread after ten seconds without a checkpoint. The held failure screen
names the last operation and retains DMAC control/status/PCR, GIF CHCR/QWC/MADR/
TADR and status, VIF/SIF channel state, and GS CSR. No filesystem or network work
is used by this failure path. Checkpoints cover loading upload, DMA, FINISH,
vsync, UI stat/open/read, menu textures/upload, card loading and sound setup.
The watchdog disarms on first menu presentation or a gameplay handoff/frame.
Release builds do not contain this diagnostic thread.

A separate, never-to-be-installed test ELF was patched into a CPU self-loop
immediately after hcu_boot_diag_begin returned. Its watchdog suspended the main
thread and displayed STAGE 3 ERROR -100 / TIMEOUT 10 seconds in STAGE/result.
The captured screen was inspected at menu-watch-hang/watchdog-held.png. Patch
address and original/replacement instructions are retained in injection.json.
Normal full BIOS menu startup with HostFs disabled and memory-placement checks
also passes. The focused bridge/storage/reader tests still pass (three tests).
Hardware diagnosis of the loading-screen stall remains pending.

Prepared image: menu-watch-assets/HALO_MENU_WATCH.iso, SHA-256
`eafcbf835ed4fca0d401b9e944a69739915346e7218281a83833d88fa66c4c56`.
A twelve-second normal-menu observation also passes, exceeding the watchdog's
ten-second threshold and confirming no spurious timeout after menu presentation
in PCSX2. Physical watchdog reporting remains to be checked on the console.

### Watchdog diagnostic installed and verified

The reconnected NBD session passed preflight against all 98 existing APA entries
with 384 MB free. `Halo Menu Watch` installed in one new 128 MB slot,
`PP.HPSX-00001..HALO_MENU_WATCH`. Post-install comparison confirms all 98 prior
entries unchanged, 99 total entries and 256 MB free. Full extracted-image SHA-256
matches `eafcbf835ed4fca0d401b9e944a69739915346e7218281a83833d88fa66c4c56`.
Hardware startup/timeout observation remains pending.

### Physical loading-bar completion and sound-startup stall

The user launched `Halo Menu Watch` from the PS2's APA HDD. The loading bar
reached its right edge, but the menu did not appear. The watchdog held a visible
failure screen: `STAGE 8 ERROR -100`, `TIMEOUT 10 seconds in: menu SPU`, site
`src/stream/hcu_boot_diag.c:52`. This establishes that texture loading,
loading-screen completion, menu asset upload, and card-loading setup returned
far enough to reach the sound-init call. It does not yet identify whether the
block is IOP module loading, the sound RPC, IOP heap setup, bank reading, or a
SPU2 transfer. The CP0 EPC/BadVAddr fields on the screen are expressly stale
and do not locate the stalled instruction.

Added sound-startup checkpoints around the embedded libsd/sdrdrv module calls,
remote initialization, mixer setup, IOP heap allocation, bank open/read, and
SPU2 transfer/status calls. The next diagnostic image is `Halo SPU Trace`,
`build/opl-qualification/menu-spu-trace-assets/HALO_SPU_TRACE.iso`, SHA-256
`78055174962d8d47f107b40a47060857f4e4acaec0f96bbb17335412891cc368`.
It retains the menu-only asset set and is not a gameplay acceptance image.
Three focused host tests pass. Physical installation and observation are
pending.

`Halo IOP Read` installed as `PP.HPSX-00001..HALO_IOP_READ`. Preflight
matched 92 entries and 2688 MB free; post-install comparison confirmed all
92 prior entries unchanged and exactly one new slot (93 total entries).
The subsequent readback stopped at 34%; its hdl_dump extraction child was
blocked in kernel folio_wait_bit_common while NBD TCP still appeared
established. The installer was stopped and its read-only child sent SIGKILL
before requesting reconnection. No reinjection is needed. Full readback
verification remains pending; see hardware/iop-read-installation.json.

### Physical IOP checkpoint read succeeds; sdrdrv reaches return

The user launched the installed IOP Read build and reports a held failure
`STAGE 8 ERROR -100 / TIMEOUT 10 seconds in: sdr returning`. This establishes
that the corrected checkpoint read works in this run and that the IOP driver
advanced through registration, thread creation/start, and its exit print to
the checkpoint immediately before return 2. It does not establish completion
of that return, a loadfile RPC reply, or sound initialization on the EE.
Earlier export-registration attribution was premature; registration is no
longer the last observed startup operation with the corrected read.

Although full ISO verification was interrupted, the local extracted prefix
contains the complete packaged menu ELF, byte-identical to the intended
runtime (`5fa1f2de211a51877213eb4ed68784c79ecfbe0b7c06ae16790ec0b0caa69638`).
The whole interrupted ISO hash differs, so it remains unverified as a full
disc image. Details: hardware/iop-read-partial-identity.json.

Prepared `Halo SDR Resident` changing only the startup return from 2 to 0
in the instrumented audit driver. In the pinned modload source these select
removable-resident and ordinary-resident flags respectively. Whether this
distinction explains the physical console's stalled completion is a hypothesis;
the actual ROM/modload identity remains unrecorded. Source diff confirms the
one-line functional change. ISO SHA-256:
`d3e711edf61cb7c36ef37df0f9331e0ca40e3afe5cb06e5a4a4464ed473ae944`.
The exact image passed PCSX2 BIOS disc boot with HostFs disabled, physical
placement checks, and 12.02 seconds of stable menu. The guest log records
sdrdrv start result 0, verifying that the intended return-value variant was
embedded and executed. Physical comparison remains pending.

After reconnection, the prior Halo IOP Read installation was fully extracted
to `hardware/readback/HALO_IOP_READ_verified.iso`; its full SHA-256 now
matches the prepared image. The earlier incomplete extraction is retained.
`hardware/iop-read-installation.json` records the completed verification.

`Halo SDR Resident` installed after preflight matched 93 entries and 2560 MB
free. Its APA identifier is truncated to
`PP.HPSX-00001..HALO_SDR_RESIDEN`. The initial installer stopped at its overly
long expected-name assertion after slot creation; verification resumed using
the exact observed ID without reinjection. All 93 prior entries remained
unchanged, exactly one slot was added (94 total), and the full extracted ISO
SHA-256 matches
`d3e711edf61cb7c36ef37df0f9331e0ca40e3afe5cb06e5a4a4464ed473ae944`.
Evidence: `hardware/sdr-resident-installation.json`. Physical comparison of
the return-value change remains pending.

### Physical menu success and full-map build

The user reports Halo SDR Resident's menu works exactly as in PCSX2 and
requests the full game with maps for menu-to-match tests. This is a physical
menu success for the tested launch route. It is not yet the repeated-launch,
all-map, controls/audio/settings, or gameplay-duration acceptance gate.

The full build rebuilds every guest with the corrected Xbox/EE thread symbol
ownership, cdrom virtual-disc profile, asset metadata fix, resident-return sound
driver, and held diagnostic screen. Menu handoff now records IOP reset, RPC
reinitialization, loadfile setup, and ELF execution with the watchdog active.
The first fully instrumented Blood Gulch link exceeded the fixed file-backed
boundary by 13572 bytes. A separately keyed -Oz CE comparison produced
identical code; that build-profile experiment was removed. The fixed reserve
and capacities remain intact. The gameplay build instead packs its generated
bootstrap metadata with the existing LZ4 codec, checks a generator round trip,
and retains the original decoded metadata SHA-256 check. Its decoded buffer
is NOBITS and charged by the existing resident ledger. Compact gameplay
diagnostics retain watchdog stages, exception handling, and held screens,
while omitting the special IOP-library audit decoder and long per-site reason
strings. Source file/line and numeric results remain visible on check failures.
The menu retains full diagnostics and the physically qualified driver.

### Full rebuilt map image ready for physical transfer

The packed-module path initially failed after an actual menu handoff in
PCSX2: the guest reached its entry with correct arguments and memory bounds,
then IOMANX load returned KE_ILLEGAL_OBJECT (-201). This was not proof of an
inherited-service failure. The packing and compact defines had been added
before a later EE_CFLAGS assignment, which discarded them. Moved the defines
after that assignment and added a link guard requiring hcu_irx_unpack in a
packed build. Rebuilt every guest and the menu after the correction. The
rejected R1 ISO and an incomplete disk-full copy were removed to recover
workspace space; their reports, ELF evidence, and hashes remain preserved.
The frozen baseline remains intact.

Lossless packing uses the existing engine LZ4 codec for bootstrap metadata
and four embedded IOP modules. Module decode uses one shared 16 KiB aligned
NOBITS scratch buffer, waits for the synchronous load to complete before
reuse, validates output lengths, and zeroes DMA padding. All NOBITS remains
charged to resident_gameplay. The file-backed limit and reserve boundary
are unchanged. The gameplay sound driver removes diagnostic tracing/auditing
but retains the qualified ordinary-resident return and interrupt-wrapper
configuration. The menu retains its qualified instrumented driver.

Current artifact: `build/opl-qualification/full-game-r1/HALO_FULL_TEST_R2.iso`
(1729507328 bytes), SHA-256
`bc5aa46e9e99594df37868305e454df75121ccb49a3f24d18663aed060bf32f7`.
All 14 ELFs were rebuilt and embedded exactly; every ELF passes necessary
placement and region-capacity checks. The smallest necessary reserve
headroom is 8906 bytes, with runtime allocation bounds verified for the
tested Blood Gulch guest. All file extents remain fixed. All map data and
HCP packages match the frozen baseline; 13 current fully resident sound
banks were separately pinned and substituted. The other 41 files remain
byte-identical. The independent ISO inventory and BIOS directory checks pass.
Source archive, dirty diffs, build reports, package hashes and test evidence
are retained beside qualification.json.

PCSX2 full BIOS disc startup with HostFs disabled passes. Window-scoped
controller tests launched Blood Gulch through the real menu, IOP reset and
LoadExecPS2 path for both one player and two players. Logs verify map/rules,
player count and render profile, then successful CE map load and gameplay
ticks. Each match was observed for 15 seconds; both gameplay screenshots
were inspected, including the two split-screen views. The harness uses the
documented Start action on START GAME. These are short emulator smoke tests,
not physical gameplay or performance acceptance. Forty focused tests pass;
one test requiring a missing historical Sidewinder artifact is deselected.

The user chose Ethernet for the full installation after being informed of
the approximate 75-minute transfer-plus-readback estimate at measured speeds.
Prepared install_full_r2.py preserves the 94 existing APA entries and uses
temporary readback space on /tmp because the workspace disk is nearly full.
Physical transfer and all-map hardware qualification remain pending.

### Interrupt-wrapper comparison failed; bounded library audit prepared

The user reports `Halo SDR IRQ` still times out in `sdr exports`. Removing
the outer interrupt suspension did not resolve registration. Treat the
interrupt-wrapper hypothesis as unsupported by this comparison. The reported
bottom-right `SIF0/1/2` label is the watchdog's final DMA snapshot, not a
different last-operation checkpoint.

Prepared `Halo SDR Audit` with bounded read-only checks before registration:
export magic, IOP pointer ranges/alignment, registered-library cycles (up to
256 entries), whether the export table is already registered, and whether
RegisterLibraryEntries' resolved import jump matches loadcore export ordinal
6. New checks import GetLoadcoreInternalData through the documented ordinal 3.
Detected problems stop in the diagnostic driver with a named EE watchdog
reason. The trace retains export address/magic, library count/head/problem
node, import instruction, actual target, and expected target. If checks pass,
the original registration call proceeds. These checks cover the registered
export chain; they do not yet audit loadcore's unresolved-import chain or
every client linkage. Production driver selection remains unchanged.
ISO SHA-256: `f14c2d977df3f7a747744335ba3fd9294ec7139def8111dbc22417d75a2072d6`.
The exact audit ISO passed full BIOS ISO boot in PCSX2 with HostFs disabled,
linked/runtime physical-placement checks, and twelve seconds of stable menu.
The new bounded checks did not reject that environment. Physical results
remain pending.

`Halo SDR Audit` subsequently installed as `PP.HPSX-00001..HALO_SDR_AUDIT`.
Preflight matched all 90 existing entries and 2944 MB free. All 90 prior
entries remained unchanged, with exactly one new slot (91 total entries).
Full readback SHA-256 matches
`f14c2d977df3f7a747744335ba3fd9294ec7139def8111dbc22417d75a2072d6`.
Evidence: `hardware/sdr-audit-installation.json`. Physical audit checkpoint
observation remains pending.

### AV signal loss after audit timeout

The user reports the audit image loads and times out, but the AV signal is
lost before the error reason can be read, and does not return after 30
seconds. The connection is AV cables. No audit result can be inferred from
this run. Inspection found SDK init_scr resets the GS, selects CRT timing
from ROM region, and resets the whole DMA controller. The game explicitly
uses interlaced NTSC. A timing transition or disruption in this failure path
is a hypothesis; the cause of the physical signal loss is unconfirmed.

Added a diagnostic-only SDK renderer extension that shares the pinned debug
font/packet implementation but reclaims only GIF for the held error screen.
It preserves GS CRT timing and leaves D_CTRL/D_STAT/D_PCR and SIF channels
untouched. Ordinary initial debug setup is unchanged. Failure and exception
screens use the held initialization. The IOP audit IRX remains byte-identical.
Prepared `Halo AV Hold`, ISO SHA-256
`370ddececb7f1fe203fb81ba0d9302edaa635809ebd728539480c8f97868c7fe`.
Normal BIOS disc boot in PCSX2 with HostFs disabled and physical-placement
checks passed with twelve seconds of stable menu. Physical AV behavior
remains pending.

The held-screen path was exercised with a separate never-install ELF patched
to loop at the menu's sound-init call, after loading-screen completion. Its
watchdog displayed `STAGE 8 ERROR -100 / TIMEOUT 10 seconds in: menu SPU`.
The captured `menu-av-hang/watchdog-held.png` was inspected: the error and
both trace columns remain visible, with PCSX2 reporting 59.94 Hz. The patch
site and original/replacement bytes are retained in injection.json. This
checks the new drawing path in PCSX2; physical AV acceptance remains open.

`Halo AV Hold` installed as `PP.HPSX-00001..HALO_AV_HOLD`. Preflight
matched all 91 existing entries and 2816 MB free; post-install comparison
confirmed all prior entries unchanged and exactly one new slot (92 total).
Full readback SHA-256 matches
`370ddececb7f1fe203fb81ba0d9302edaa635809ebd728539480c8f97868c7fe`.
Evidence: `hardware/av-hold-installation.json`. Physical AV stability and
the IOP audit checkpoint remain pending.

### Physical EE fault in diagnostic IOP read

The user could read the held AV screen and reported `HALO BOOT EXCEPTION`,
stage 8/result 0, cause `70008010`, EPC `00148c5c`, BadVAddr `bc03da00`.
Exact-ELF addr2line and disassembly resolve this to boot_watchdog's first
`lw` from the directly mapped IOP checkpoint. This is an agent-introduced
diagnostic access bug, not evidence of a new Halo asset or sound fault.
The SDK smem_read implementation disables interrupts, enters EE kernel mode,
copies from SUB_VIRT_MEM, exits kernel mode, and enables interrupts. The
diagnostic's direct dereference omitted that privilege transition.

Replaced direct reads with smem_read into an aligned 64-byte local snapshot.
Prepared `Halo IOP Read`, ISO SHA-256
`39f4d8c44ae1494aa93ea85ad0ed4f3e45da7d6a9b301bbb0459482d253eb8b3`.
The held AV display and audit IRX remain unchanged. The diagnostic IRX build
rule now forces regeneration when a custom driver is selected, preventing
seeded objects from retaining a different driver merely because its input
timestamp is older. A separate never-install IOP self-test deliberately
stalls after writing its checkpoint to exercise the actual timeout memory
read, rather than only an EE loop before IOP tracing is active.

The exact corrected ISO passed PCSX2 BIOS disc boot with HostFs disabled,
physical-placement checks, and 12.02 seconds of stable menu. The separate
IOP-stall self-test displayed `TIMEOUT 10 seconds in: IOP diagnostic read
self-test` with checkpoint 26 and populated export/library/import values;
no EE exception occurred. The held screenshot
`menu-iop-selftest/watchdog-held.png` was inspected. This self-test ISO is
never to be installed. Physical verification of the corrected read remains
pending.

### Physical sdrdrv load/start checkpoint and IOP instrumentation

The user reports `Halo SPU Load` timed out in `sdr load/start`. Thus the
sdrdrv image allocation, cache writeback, and SIF DMA completed. The blocking
loadfile request did not return; this still does not prove entry into sdrdrv.

Prepared `Halo SDR Entry` with a separately built diagnostic copy of the
pinned SDK driver. Its startup records checkpoints before interrupt suspension,
export registration, interrupt restoration, banner printing, thread creation,
thread start, exit printing, and return. A separate word records RPC thread
initialization, queue registration, server registration, and RPC loop entry.
The EE supplies a dedicated 64-byte IOP allocation through a module argument.
The watchdog reads this allocation through the SDK-documented IOP memory
window (`smem.h`, SUB_VIRT_MEM) and displays a named startup checkpoint.
The installed SDK and its source snapshot are unchanged. The custom driver is
selected only for this diagnostic build; release module loading is unchanged.

ISO: `menu-sdr-entry-assets/HALO_SDR_ENTRY.iso`, SHA-256
`79c48ff629b4674acab5d8a215771477055dce53c1ec3f801713bdf7f2cbb16c`.
Full BIOS ISO boot in PCSX2 with HostFs disabled passed the presented-menu
marker, physical-placement checks, and 12.02 seconds of stable menu. Source
and custom IRX hashes are retained in package.json. Hardware checkpoint
observation remains pending.

APA diagnostic capacity is exhausted after Halo SPU Load. The retained
hdl_dump build disables its deletion command (`INCLUDE_HIDE_CMD`, marked
malfunctioning upstream). No deletion was attempted. The next installation
requires removing an agent-created diagnostic slot through the console;
`Halo APA Probe1` is the oldest entry-only probe and its ISO/readback are
preserved. Original user games must remain untouched.

The user explicitly requested network deletion of the old diagnostics.
Further inspection distinguished the disabled hide command from the library's
separate `apa_delete_partition` routine. A dedicated helper uses an exact
allowlist of the 13 agent-created partition IDs, without title lookup or
wildcards. All 369 current linked APA headers were backed up in
`hardware/apa-headers-before-cleanup.json`. The deletion routine was tested
on a local sparse copy: all 88 original main entries and all 352 surviving
headers' payloads matched (only checksum/next/previous fields change).

After a fresh inventory match, the same cleanup committed over NBD.
The post-cleanup TOC exactly matches the original 88 entries, with 3200 MB
free. All local diagnostic ISO/readback artifacts remain preserved.
Evidence is in `hardware/cleanup-offline-validation.json`,
`diagnostic-cleanup.json`, and `apa-toc-after-cleanup.txt`.

`Halo SDR Entry` installed as `PP.HPSX-00001..HALO_SDR_ENTRY`, leaving
89 main entries (88 originals plus this diagnostic). Full readback SHA-256
matches `79c48ff629b4674acab5d8a215771477055dce53c1ec3f801713bdf7f2cbb16c`.
All 88 original entries remain unchanged. Installation/readback evidence is
in `hardware/sdr-entry-installation.json`. Physical IOP checkpoint reporting
remains pending.

### Physical IOP export-registration stall

The user reports `Halo SDR Entry` timed out in `sdr exports`. The IOP
checkpoint proves driver entry and completion of the outer CpuSuspendIntr
call; the checkpoint immediately after RegisterLibraryEntries was not reached.
The stale CP0 fields on the EE watchdog do not identify an IOP instruction.

Prepared `Halo SDR IRQ` as a controlled comparison: remove only the outer
CpuSuspendIntr/CpuResumeIntr pair around startup export registration in the
instrumented driver. RegisterLibraryEntries itself remains in place, as do
the export table, RPC thread, and sound operations. The pinned loadcore source
manages its own interrupt context, and bundled FreeSD calls registration
without the outer pair. This motivates a hypothesis about interrupt context;
the actual console ROM implementation and physical result remain unverified.
Source diff confirms the only functional driver change is that pair's removal.
ISO SHA-256: `73a16ec4cc4b8e83a9f47c9974cf2ada287d2bd45eb0cc15a7d6bd9e086aaa80`.
The SDK installation and production driver selection remain unchanged.
The exact comparison ISO passed PCSX2 full BIOS disc boot with HostFs
disabled, linked/runtime memory placement, and twelve seconds of stable menu.
Physical comparison remains pending.

`Halo SDR IRQ` installed as `PP.HPSX-00001..HALO_SDR_IRQ` after preflight
matched all 89 existing entries and 3072 MB free. Post-install verification
confirmed all prior entries unchanged and exactly one new slot (90 total).
Full readback SHA-256 matches
`73a16ec4cc4b8e83a9f47c9974cf2ada287d2bd45eb0cc15a7d6bd9e086aaa80`.
Evidence: `hardware/sdr-irq-installation.json`. Physical comparison remains
pending.

The exact final SPU trace image passed PCSX2 full BIOS ISO boot with HostFs
disabled, reached the presented-menu marker, and remained stable for 12.02
seconds. Linked/runtime physical placement checks passed. The installation
precheck found `/dev/nbd0` disconnected (0 bytes and no NBD TCP connection),
so no APA writes were attempted.

After the user reconnected the NBD server, preflight matched all 99 prior
entries and 256 MB free. `Halo SPU Trace` installed as
`PP.HPSX-00001..HALO_SPU_TRACE`. All 99 prior entries remained unchanged;
the drive now has 100 entries. Full extracted ISO SHA-256 matched
`78055174962d8d47f107b40a47060857f4e4acaec0f96bbb17335412891cc368`.
The installation report is `hardware/spu-trace-installation.json`.
Physical launch and the more specific sound checkpoint remain pending.

### Physical sdrdrv load stall

The user reports `Halo SPU Trace` held `STAGE 8 ERROR -100`,
`TIMEOUT 10 seconds in: sdrdrv`. The preceding libsd load returned a positive
module ID with a start result accepted by the current loader. The sdrdrv
`SifExecModuleBuffer` call did not return. Sound RPC initialization and bank
upload had not begun. This does not yet prove that the sdrdrv module's own
entry point ran: the EE helper also allocates IOP RAM, transfers the image,
invokes loadfile, and frees the transfer buffer.

Prepared `Halo SPU Load` with diagnostic-only checkpoints between those same
SDK operations. The release path retains `SifExecModuleBuffer`; the diagnostic
path uses the pinned SDK sequence and public `SifLoadStartModuleBuffer`, keeping
the IOP transfer buffer alive until the blocking load returns. Labels identify
heap allocation, cache writeback, DMA submission/completion, load/start, and
heap cleanup separately for libsd and sdrdrv. No IOP reset is added.
ISO SHA-256: `786f80016100f188e1d6c96b8d2f41786421ece8b798743ca8330b6d87755e3f`.
The exact image passed PCSX2 full BIOS disc boot with HostFs disabled,
physical placement checks, and 12.02 seconds of stable presented menu.
Installation and physical results remain pending.

`Halo SPU Load` subsequently installed as `PP.HPSX-00001..HALO_SPU_LOAD`.
Preflight matched all 100 prior entries; post-install comparison confirmed
those entries unchanged and exactly one addition (101 total entries).
Full readback SHA-256 matches the prepared image above. The report is
`hardware/spu-load-installation.json`. Physical checkpoint observation is
pending.
