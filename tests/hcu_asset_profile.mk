include tools/hcu-asset-profile.mk
.PHONY: print-root
print-root:
	@printf '%s\n' '$(WORLD_HCU_ASSET_ROOT)'
