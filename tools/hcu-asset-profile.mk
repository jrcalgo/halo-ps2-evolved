# Fixed, deterministic roots for the combined HCU machine image. OPL itself is
# not linked. opl-iso uses the virtual disc on every OPL backing device.
# opl-usb/opl-smb/opl-hdd are standalone-file profiles, not installed ISOs.
ifeq ($(WORLD_HCU_ASSET_PROFILE),host)
WORLD_HCU_ASSET_ROOT := host:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-iso)
WORLD_HCU_ASSET_ROOT := cdrom:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),optical)
WORLD_HCU_ASSET_ROOT := cdrom:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-usb)
WORLD_HCU_ASSET_ROOT := mass:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-smb)
WORLD_HCU_ASSET_ROOT := smb0:/
else ifeq ($(WORLD_HCU_ASSET_PROFILE),opl-hdd)
WORLD_HCU_ASSET_ROOT := pfs0:/
else
$(error Unsupported WORLD_HCU_ASSET_PROFILE '$(WORLD_HCU_ASSET_PROFILE)'; choose host, optical, opl-iso, opl-usb, opl-smb, or opl-hdd)
endif
