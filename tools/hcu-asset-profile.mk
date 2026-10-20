# Fixed, deterministic roots for the combined HCU machine image. OPL itself is
# not linked; these select filesystems it may leave mounted for the ELF.
ifeq ($(WORLD_HCU_ASSET_PROFILE),host)
WORLD_HCU_ASSET_ROOT := host:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),optical)
WORLD_HCU_ASSET_ROOT := cdrom:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-usb)
WORLD_HCU_ASSET_ROOT := mass:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-smb)
WORLD_HCU_ASSET_ROOT := smb0:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-hdd)
WORLD_HCU_ASSET_ROOT := pfs0:/
else
$(error Unsupported WORLD_HCU_ASSET_PROFILE '$(WORLD_HCU_ASSET_PROFILE)'; choose host, optical, opl-usb, opl-smb, or opl-hdd)
endif
