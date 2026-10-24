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
WORLD_HCU_RENDER_CLEAR_TEST ?= 0
WORLD_HCU_ANIMATION_TRACE_TEST ?= 0
# HCU_LOAD_TRACE=1 prints HALO_PS2_LOCAL load-trace phase lines (off by default).
HCU_LOAD_TRACE ?= 0
WORLD_HCU_M2_UI_LIFECYCLE_TEST ?= 0
WORLD_HCU_STEP8_MP_CAPACITY_DIAGNOSTIC ?= 0
WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS ?= 2
# Partition row (hcu_memory_partition_select_v2) whose generated production image
# header is built in. Empty keeps the bootstrap partition.
WORLD_HCU_PARTITION_PROFILE ?=
WORLD_HCU_HEADLESS_RUNTIME_GUEST ?=0
WORLD_HCU_PROFILE_PACKAGE_ROOT ?=build/m2-c2-r3-selected-packages/pkg
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
	$(WORLD_OUTPUT)/stream/hcu_load_trace.o \
	$(WORLD_OUTPUT)/stream/hcu_profile_mount.o \
	$(WORLD_OUTPUT)/stream/hcu_profile_metadata.o \
	$(WORLD_OUTPUT)/stream/hcu_asset_profile.o \
	$(WORLD_OUTPUT)/stream/hcu_bitmap_quad.o \
	$(WORLD_OUTPUT)/stream/hcu_pose_asset.o \
	$(WORLD_OUTPUT)/stream/hcu_bitmap_dispatch.o \
	$(WORLD_OUTPUT)/stream/hcu_bitmap_frame.o \
	$(WORLD_OUTPUT)/stream/hcu_bitmap_renderer.o \
	$(WORLD_OUTPUT)/stream/hcu_bitmap_attach.o \
	$(WORLD_OUTPUT)/stream/hcu_owner_telemetry.o \
	$(WORLD_OUTPUT)/stream/hcu_render_telemetry.o \
	$(WORLD_OUTPUT)/stream/hcu_map_catalog.o \
	$(WORLD_OUTPUT)/stream/hcu_filexio_irx.o \
	$(WORLD_OUTPUT)/stream/ctag_ps2_backend.o
WORLD_FILEXIO := 1
# C3 (opt-in HCU_C3=1): snapshot bank, sound-request recorder, render content and frame layout.
ifeq ($(HCU_C3),1)
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_snapshot_bank.o \
	$(WORLD_OUTPUT)/stream/hcu_sound_requests.o \
	$(WORLD_OUTPUT)/stream/hcu_render_content.o \
	$(WORLD_OUTPUT)/stream/hcu_render_frame.o \
	$(WORLD_OUTPUT)/stream/hcu_render_media.o \
	$(WORLD_OUTPUT)/stream/hcu_render_world.o \
	$(WORLD_OUTPUT)/stream/hcu_render_views.o
endif
else
EE_OBJS += $(WORLD_OUTPUT)/main.o
endif
ifeq ($(WORLD_STREAM_DIAGNOSTIC),1)
EE_OBJS += $(WORLD_OUTPUT)/hybrid/staging.o $(WORLD_OUTPUT)/hybrid/reader_ee.o $(WORLD_OUTPUT)/hybrid/viewer_diagnostic.o
$(WORLD_OUTPUT)/main.o: EE_CFLAGS += -DHALO_STREAM_DIAGNOSTIC -Dbsp_render_build=hybrid_stream_build
ifeq ($(WORLD_HCU_HEADLESS_RUNTIME_GUEST),1)
$(WORLD_OUTPUT)/main.o: EE_CFLAGS += -DHALO_PS2_C2_PRODUCTION_RUNTIME_GUEST=1
endif
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
# Compile the parent-to-HCU arena binders for the combined-link probe or an
# explicitly profiled HCU play target. The stock viewer does not depend on HCU.
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_memory_bind.o \
	$(WORLD_OUTPUT)/stream/hcu_memory_profile.o
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

# C2.4: a selected partition row names its generated image header. The header
# pins that row's package, metadata, source maps and datum table.
$(WORLD_OUTPUT)/c2/%.h: tools/c2_profile_image_header.py
	@mkdir -p $(@D)
	python3 -I tools/c2_profile_image_header.py --row $* \
		--package-root "$(WORLD_HCU_PROFILE_PACKAGE_ROOT)" --output $@

$(WORLD_OUTPUT)/stream/hcu_main.o: src/stream/hcu_main.c hcu-profile-force \
	$(if $(WORLD_HCU_PARTITION_PROFILE),$(WORLD_OUTPUT)/c2/$(WORLD_HCU_PARTITION_PROFILE).h)
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar -I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-DHALO_HCU_TAG_CACHE_BYTES=$(WORLD_HCU_TAG_CACHE_BYTES) \
		-DHALO_HCU_ASSET_ROOT=\"$(WORLD_HCU_ASSET_ROOT)\" \
		$(if $(WORLD_HCU_PARTITION_PROFILE),-DHALO_HCU_PARTITION_PROFILE=\"$(WORLD_HCU_PARTITION_PROFILE)\" -DHALO_HCU_PROFILE_IMAGE_HEADER=\"$(WORLD_HCU_PARTITION_PROFILE).h\" -I$(WORLD_OUTPUT)/c2,) \
		$(if $(filter 1,$(WORLD_HCU_HEADLESS_RUNTIME_GUEST)),-DHALO_HCU_HEADLESS_RUNTIME_GUEST=1,) \
		$(if $(filter 1,$(WORLD_HCU_HEADLESS_RUNTIME_GUEST)),-DHALO_PS2_C2_PRODUCTION_RUNTIME_GUEST=1,) \
		$(if $(filter 1,$(WORLD_HCU_RENDER_CLEAR_TEST)),-DHALO_PS2_M3_RENDER_CLEAR_TEST=1,) \
		$(if $(filter 1,$(WORLD_HCU_STEP8_MP_CAPACITY_DIAGNOSTIC)),-DHALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC=1,) \
		$(if $(filter 2 4,$(WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS)),-DHALO_PS2_STEP8_MP_WORKLOAD_PLAYERS=$(WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS),) \
		$(if $(filter 1,$(WORLD_HCU_ANIMATION_TRACE_TEST)),-DHALO_PS2_M2_ANIMATION_TRACE=1,) \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_file_bridge.o: src/stream/hcu_file_bridge.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_load_trace.o: src/stream/hcu_load_trace.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc $(if $(filter 1,$(HCU_LOAD_TRACE)),-DHCU_LOAD_TRACE=1 -DHCU_LOAD_TRACE_EE=1,) -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_map_service.o: src/stream/hcu_map_service.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		$(if $(filter 1,$(HCU_LOAD_TRACE)),-DHCU_LOAD_TRACE=1,) \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		$(if $(filter 1,$(WORLD_HCU_HEADLESS_RUNTIME_GUEST)),-DHALO_HCU_HEADLESS_RUNTIME_GUEST=1,) \
		$(if $(filter 1,$(WORLD_HCU_M2_UI_LIFECYCLE_TEST)),-DHALO_PS2_M2_UI_LIFECYCLE_TEST=1,) \
		$(if $(filter 1,$(WORLD_HCU_STEP8_MP_CAPACITY_DIAGNOSTIC)),-DHALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC=1,) \
		$(if $(filter 2 4,$(WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS)),-DHALO_PS2_STEP8_MP_WORKLOAD_PLAYERS=$(WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS),) \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_profile_mount.o: src/stream/hcu_profile_mount.c src/stream/hcu_profile_mount.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		$(if $(filter 1,$(HCU_LOAD_TRACE)),-DHCU_LOAD_TRACE=1,) \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_profile_metadata.o: src/stream/hcu_profile_metadata.c src/stream/hcu_profile_metadata.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/ps2_ctag.o: $(HCU_ROOT)/port/ps2/src/ps2_ctag.c $(HCU_ROOT)/port/ps2/include/ps2_ctag.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_asset_profile.o: src/stream/hcu_asset_profile.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc $(if $(filter 1,$(HCU_LOAD_TRACE)),-DHCU_LOAD_TRACE=1,) -fshort-wchar \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bitmap_quad.o: src/stream/hcu_bitmap_quad.c src/stream/hcu_bitmap_quad.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) -std=c11 $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_pose_asset.o: src/stream/hcu_pose_asset.c src/stream/hcu_pose_asset.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bitmap_dispatch.o: src/stream/hcu_bitmap_dispatch.c src/stream/hcu_bitmap_dispatch.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bitmap_frame.o: src/stream/hcu_bitmap_frame.c src/stream/hcu_bitmap_frame.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bitmap_renderer.o: src/stream/hcu_bitmap_renderer.c src/stream/hcu_bitmap_renderer.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bitmap_attach.o: src/stream/hcu_bitmap_attach.c src/stream/hcu_bitmap_renderer.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_owner_telemetry.o: src/stream/hcu_owner_telemetry.c src/stream/hcu_owner_telemetry.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_render_telemetry.o: src/stream/hcu_render_telemetry.c src/stream/hcu_render_telemetry.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_map_catalog.o: src/stream/hcu_map_catalog.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

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
ifeq ($(HCU_C3),1)
$(WORLD_OUTPUT)/stream/hcu_snapshot_bank.o: src/stream/hcu_snapshot_bank.c src/stream/hcu_snapshot_bank.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_sound_requests.o: src/stream/hcu_sound_requests.c src/stream/hcu_sound_requests.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_render_content.o: src/stream/hcu_render_content.c src/stream/hcu_render_content.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_render_views.o: src/stream/hcu_render_views.c src/stream/hcu_render_views.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_render_frame.o: src/stream/hcu_render_frame.c src/stream/hcu_render_frame.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@
$(WORLD_OUTPUT)/stream/hcu_render_media.o: src/stream/hcu_render_media.c src/stream/hcu_render_media.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) -D_EE $(EE_INCS) -I$(ENGINE)/src -Isrc \
		-I$(PS2SDK)/ee/include -I$(PS2SDK)/common/include \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_render_world.o: src/stream/hcu_render_world.c src/stream/hcu_render_world.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) -D_EE $(EE_INCS) -I$(ENGINE)/src -Isrc \
		-I$(PS2SDK)/ee/include -I$(PS2SDK)/common/include \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@
endif
endif

$(WORLD_OUTPUT)/stream/hcu_memory_bind.o: src/stream/hcu_memory_bind.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-fshort-wchar -I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_memory_profile.o: src/stream/hcu_memory_profile.c
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
EE_CFLAGS += $(EE_OPTFLAGS)
# C3 umbrella (opt-in): the parent and the CE port compile the same frame-snapshot path.
HCU_C3 ?= 0
ifeq ($(HCU_C3),1)
EE_CFLAGS += -DHCU_C3=1 -DHCU_C3_FRAME_SNAPSHOT -DHALO_PS2_C3_FRAME_SNAPSHOT
endif
# C3.objects (opt-in, needs HCU_C3=1): the object pass draws the published snapshot. HCU_C3_OBJECTS_SYNTHETIC=1
# publishes a synthetic object snapshot until the CE publisher fills the bank. The table header is generated
# per package by tools/hcu_c3_objects_table.py into HCU_C3_OBJECTS_GEN.
HCU_C3_OBJECTS ?= 0
HCU_C3_OBJECTS_SYNTHETIC ?= 0
HCU_C3_OBJECTS_GEN ?= build/c3/objects/gen
ifeq ($(HCU_C3_OBJECTS),1)
EE_CFLAGS += -DHCU_C3_OBJECTS=1 -DHCU_RENDER_OBJECTS_EE=1 -I$(HCU_C3_OBJECTS_GEN)
ifeq ($(HCU_C3_OBJECTS_SYNTHETIC),1)
EE_CFLAGS += -DHCU_C3_OBJECTS_SYNTHETIC=1
endif
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_render_objects.o
$(WORLD_OUTPUT)/stream/hcu_render_objects.o: src/stream/hcu_render_objects.c src/stream/hcu_render_objects.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) -D_EE $(EE_INCS) -I$(ENGINE)/src -Isrc \
		-I$(PS2SDK)/ee/include -I$(PS2SDK)/common/include \
		-I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar \
		-I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-include $(HCU_ROOT)/port/ps2/include/halo_ps2_prefix.h \
		-c $< -o $@
endif

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
