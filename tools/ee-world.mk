# Compile pinned upstream world-viewer sources into parent-owned output only.
ENGINE = submodules/halo-ps2/engine
WORLD_VIS_SOURCE ?= src/world/visibility.c
EE_BIN = $(WORLD_OUTPUT)/world.elf
EE_OBJS = $(WORLD_OUTPUT)/platform/screenshot_sdk.o \
	$(WORLD_OUTPUT)/visibility_adapter.o \
	$(WORLD_OUTPUT)/core/config.o \
	$(WORLD_OUTPUT)/core/mat.o \
	$(WORLD_OUTPUT)/core/mem.o \
	$(WORLD_OUTPUT)/platform/fbdump.o \
	$(WORLD_OUTPUT)/platform/pad.o \
	$(WORLD_OUTPUT)/platform/profiler.o \
	$(WORLD_OUTPUT)/platform/video.o \
	$(WORLD_OUTPUT)/sim/fpview.o \
	$(WORLD_OUTPUT)/sim/objects.o \
	$(WORLD_OUTPUT)/sim/skeleton.o \
	$(WORLD_OUTPUT)/render/bsp_render.o \
	$(WORLD_OUTPUT)/render/camera.o \
	$(WORLD_OUTPUT)/render/chain.o \
	$(WORLD_OUTPUT)/render/clip.o \
	$(WORLD_OUTPUT)/render/flycam.o \
	$(WORLD_OUTPUT)/render/lodctl.o \
	$(WORLD_OUTPUT)/render/obj_render.o \
	$(WORLD_OUTPUT)/render/selftest.o \
	$(WORLD_OUTPUT)/render/text.o \
	$(WORLD_OUTPUT)/render/texcache.o \
	$(WORLD_OUTPUT)/render/upload.o \
	$(WORLD_OUTPUT)/render/vis.o \
	$(WORLD_OUTPUT)/stream/file.o \
	$(WORLD_OUTPUT)/stream/hp2.o \
	$(WORLD_OUTPUT)/stream/cbsp_catalog.o \
	$(WORLD_OUTPUT)/stream/ctag_mount.o \
	$(WORLD_OUTPUT)/stream/ctag_resource_index.o \
	$(WORLD_OUTPUT)/stream/ctag_map_source.o \
	$(WORLD_OUTPUT)/stream/sha256.o \
	$(WORLD_OUTPUT)/stream/hmap.o \
	$(WORLD_OUTPUT)/world/anim.o \
	$(WORLD_OUTPUT)/world/bsp.o \
	$(WORLD_OUTPUT)/world/model.o \
	$(WORLD_OUTPUT)/world/scen.o \
	$(WORLD_OUTPUT)/world/section.o \
	$(WORLD_OUTPUT)/world/tex.o \
	$(WORLD_OUTPUT)/world/world.o \
	$(WORLD_OUTPUT)/vu1/world.o
WORLD_HCU_GAMEPLAY ?= 0
ifeq ($(WORLD_HCU_GAMEPLAY),1)
# Optional CE machine path; the regular measured viewer remains the default.
WORLD_HCU_MEMORY_BRIDGE := 1
WORLD_HCU_TAG_CACHE_BYTES ?= 2097152
WORLD_HCU_ASSET_PROFILE ?= host
include tools/hcu-asset-profile.mk
EE_LDFLAGS += -Wl,--wrap,malloc -Wl,--wrap,free -Wl,--wrap,calloc -Wl,--wrap,realloc
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_main.o \
	$(WORLD_OUTPUT)/stream/hcu_file_bridge.o \
	$(WORLD_OUTPUT)/stream/hcu_input_bridge.o \
	$(WORLD_OUTPUT)/stream/hcu_render_snapshot.o \
	$(WORLD_OUTPUT)/stream/hcu_storage_boot.o \
	$(WORLD_OUTPUT)/stream/hcu_map_service.o \
	$(WORLD_OUTPUT)/stream/hcu_filexio_irx.o \
	$(WORLD_OUTPUT)/stream/ctag_ps2_backend.o
WORLD_FILEXIO := 1
else
EE_OBJS += $(WORLD_OUTPUT)/main.o
endif
ifeq ($(WORLD_STREAM_DIAGNOSTIC),1)
EE_OBJS += $(WORLD_OUTPUT)/hybrid/staging.o $(WORLD_OUTPUT)/hybrid/reader_ee.o $(WORLD_OUTPUT)/hybrid/viewer_diagnostic.o
$(WORLD_OUTPUT)/main.o: EE_CFLAGS += -DHALO_STREAM_DIAGNOSTIC -Dbsp_render_build=hybrid_stream_build
endif
ifeq ($(WORLD_PLAY),1)
EE_OBJS += $(WORLD_OUTPUT)/play_ee.o \
	$(WORLD_OUTPUT)/game/collpack.o $(WORLD_OUTPUT)/game/collide.o \
	$(WORLD_OUTPUT)/game/gun.o $(WORLD_OUTPUT)/game/shot.o $(WORLD_OUTPUT)/game/vital.o \
	$(WORLD_OUTPUT)/game/grenade.o $(WORLD_OUTPUT)/game/grenade_blast.o \
	$(WORLD_OUTPUT)/game/combat_targets.o \
	$(WORLD_OUTPUT)/game/move.o $(WORLD_OUTPUT)/game/pad.o $(WORLD_OUTPUT)/game/pill.o \
	$(WORLD_OUTPUT)/game/play_fp.o
EE_LDFLAGS += -Wl,--wrap,flycam_update -Wl,--wrap,profiler_overlay -Wl,--wrap,fpview_place \
	-Wl,--wrap,fpview_tick -Wl,--wrap,objects_pose_model -Wl,--wrap,objects_tick
endif
WORLD_HCU_MEMORY_BRIDGE ?= 0
ifeq ($(WORLD_HCU_MEMORY_BRIDGE),1)
# Compile the shared parent-to-HCU arena binder for the combined-link probe or
# future HCU play target. The stock viewer does not depend on HCU symbols.
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_memory_bind.o
endif

$(WORLD_OUTPUT)/hybrid/%.o: src/stream/%.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/ctag_mount.o: src/stream/ctag_mount.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/ctag_ps2_backend.o: src/stream/ctag_ps2_backend.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/cbsp_catalog.o: src/stream/cbsp_catalog.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/ctag_resource_index.o: src/stream/ctag_resource_index.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/ctag_map_source.o: src/stream/ctag_map_source.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/sha256.o: src/stream/sha256.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hmap.o: src/stream/hmap.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

HCU_ROOT = submodules/halo-ce-universal
ifeq ($(WORLD_HCU_GAMEPLAY),1)
# Always rebuild the entry object because its asset-root profile is a make
# variable and is not represented by a source-file timestamp.
.PHONY: hcu-profile-force
hcu-profile-force:

$(WORLD_OUTPUT)/stream/hcu_main.o: src/stream/hcu_main.c hcu-profile-force
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar -I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-DHALO_HCU_TAG_CACHE_BYTES=$(WORLD_HCU_TAG_CACHE_BYTES) \
		-DHALO_HCU_ASSET_ROOT=\"$(WORLD_HCU_ASSET_ROOT)\" \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_file_bridge.o: src/stream/hcu_file_bridge.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_map_service.o: src/stream/hcu_map_service.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_storage_boot.o: src/stream/hcu_storage_boot.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -DHALO_PS2=1 \
		-DHALO_FILE_USE_FILEXIO -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_filexio_irx.o: src/stream/hcu_filexio_irx.S \
	$(PS2SDK)/iop/irx/iomanX.irx $(PS2SDK)/iop/irx/fileXio.irx
	@mkdir -p $(@D)
	$(EE_CC) -G0 -x assembler-with-cpp \
		-DHALO_PS2_IOMANX_IRX=\"$(PS2SDK)/iop/irx/iomanX.irx\" \
		-DHALO_PS2_FILEXIO_IRX=\"$(PS2SDK)/iop/irx/fileXio.irx\" \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_input_bridge.o: src/stream/hcu_input_bridge.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar -I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_render_snapshot.o: src/stream/hcu_render_snapshot.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@
endif

$(WORLD_OUTPUT)/stream/hcu_memory_bind.o: src/stream/hcu_memory_bind.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-fshort-wchar -I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/play_ee.o: src/game/play_ee.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/game/%.o: src/game/%.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

EE_LIBS = -ldraw -lgraph -lpacket2 -ldma -ldebug -lpad -lmtap -lm
EE_INCS = -I$(ENGINE)/src
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Wno-unused-parameter -MMD -MP -G0 \
	-ffile-prefix-map=$(PS2SDK)=/ps2sdk
ifeq ($(WORLD_HCU_LINK_PROBE),1)
# Diagnostic-only granularity lets the combined link discard unreferenced
# parent functions/data; it does not alter behavior of retained sections.
EE_CFLAGS += -ffunction-sections -fdata-sections
EE_LDFLAGS += -Wl,--gc-sections
endif
WORLD_FILEXIO ?= 0
ifeq ($(WORLD_FILEXIO),1)
# HCU gameplay startup owns module reuse/load and FileXio initialization;
# non-HCU users selecting this reader must provide the same startup service.
EE_CFLAGS += -DHALO_FILE_USE_FILEXIO
EE_INCS += -I$(PS2SDK)/ee/rpc/filexio/include
EE_LIBS += -lfileXio
EE_LIBS += -lpatches
endif
EE_DVP = dvp-as

.PHONY: all parent-objects
all: $(EE_BIN)
parent-objects: $(EE_OBJS)
$(EE_OBJS): tools/ee-world.mk
-include $(EE_OBJS:.o=.d)

# Consume the pinned readback fix directly; the existing installed debug archive
# is otherwise unchanged. These strong symbols prevent its old screenshot.o loading.
$(WORLD_OUTPUT)/platform/screenshot_sdk.o: submodules/ps2sdk/ee/debug/src/screenshot.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(WORLD_OUTPUT)/visibility_adapter.o: $(WORLD_VIS_SOURCE)
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(WORLD_OUTPUT)/render/vis.o: $(ENGINE)/src/render/vis.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Dvis_run=halo_upstream_vis_run -c $< -o $@

$(WORLD_OUTPUT)/%.o: $(ENGINE)/src/%.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(WORLD_OUTPUT)/vu1/world.o: $(ENGINE)/src/vu1/world.vsm $(ENGINE)/src/vu1/bsp.vsm $(ENGINE)/src/vu1/model.vsm
	@mkdir -p $(@D)
	cd $(ENGINE) && $(EE_DVP) src/vu1/world.vsm -o $(abspath $@)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
