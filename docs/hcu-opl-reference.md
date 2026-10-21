# OPL reference pin and storage-path evidence

Open PS2 Loader is tracked only as an unmodified source reference in
`submodules/opl`. The parent gitlink is pinned to
`b3a2199795fe89ba7e2dd7b843354472dff2c3eb`; the canonical upstream is
`https://github.com/ps2homebrew/Open-PS2-Loader.git`. OPL is not compiled,
linked, or required by the Halo runtime. Its separate `reference_submodules`
entry in `config/dependencies.json` keeps it outside the bundle-backed build
dependency restore path.

The pinned OPL source documents support for USB mass storage, SMB shares, and
expansion-port HDDs in `submodules/opl/README.md`. It gives `mass:` as the USB
device identifier for app ELF paths (`README.md`, APPS section). The OPL SMB
implementation sets `ethBase` to `smb0:` (`src/ethsupport.c`), whereas
`labs/smblab/smblab.c` uses `smb:` for SMB control operations; therefore the
game asset profile uses the mounted share filesystem prefix `smb0:/`, not the
SMB management-device prefix. OPL's HDD code mounts `pfs0:` and uses it as its
HDD filesystem prefix (`src/hddsupport.c`).

Parent asset profiles are deterministic build selections in
`tools/ee-world.mk`:

| Profile | Root | Evidence / role |
|---|---|---|
| `host` | `host:/` | Existing development and PCSX2 host-backed profile |
| `optical` | `cdrom:/` | PS2 optical-disc profile |
| `opl-usb` | `mass:/` | OPL USB mass-storage profile |
| `opl-smb` | `smb0:/` | OPL SMB share filesystem profile |
| `opl-hdd` | `pfs0:/` | OPL expansion-HDD filesystem profile |

The host FileXio fixture verifies only path selection and bounded file API
delegation. It is not evidence that OPL leaves a particular device mounted,
that a given console has the required IRX services, or that an OPL-launched
game can load assets. Those claims still require target/PCSX2 storage-profile
smokes and deterministic missing-root diagnostics. No OPL source file has been
modified as part of this integration.
