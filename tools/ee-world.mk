# Compile pinned upstream world-viewer sources into parent-owned output only.
ENGINE = submodules/halo-ps2/engine
EE_BIN = $(WORLD_OUTPUT)/world.elf
EE_OBJS = $(WORLD_OUTPUT)/visibility_adapter.o \
	$(WORLD_OUTPUT)/main.o \
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
	$(WORLD_OUTPUT)/world/anim.o \
	$(WORLD_OUTPUT)/world/bsp.o \
	$(WORLD_OUTPUT)/world/model.o \
	$(WORLD_OUTPUT)/world/scen.o \
	$(WORLD_OUTPUT)/world/tex.o \
	$(WORLD_OUTPUT)/world/world.o \
	$(WORLD_OUTPUT)/vu1/world.o
EE_LIBS = -ldraw -lgraph -lpacket2 -ldma -ldebug -lpad -lm
EE_INCS = -I$(ENGINE)/src
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Wno-unused-parameter -MMD -MP -G0 \
	-ffile-prefix-map=$(PS2SDK)=/ps2sdk
EE_DVP = dvp-as

.PHONY: all
all: $(EE_BIN)
$(EE_OBJS): tools/ee-world.mk
-include $(EE_OBJS:.o=.d)

$(WORLD_OUTPUT)/visibility_adapter.o: src/world/visibility.c
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
