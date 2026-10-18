EE_BIN = $(HYBRID_OUTPUT)/hybrid.elf
ENGINE = submodules/halo-ps2/engine
HALO = submodules/halo-64/source
EE_OBJS = $(HYBRID_OUTPUT)/boundary.o $(HYBRID_OUTPUT)/data.o $(HYBRID_OUTPUT)/integer_math.o \
	$(HYBRID_OUTPUT)/core.o $(HYBRID_OUTPUT)/replay.o $(HYBRID_OUTPUT)/main.o \
	$(HYBRID_OUTPUT)/video.o $(HYBRID_OUTPUT)/chain.o $(HYBRID_OUTPUT)/upload.o \
	$(HYBRID_OUTPUT)/world.o
EE_CFLAGS = -std=gnu11 -DHALO_PS2=1 -fno-strict-aliasing -Wall -Wextra -Werror -Wno-multichar -G0 -MMD -MP \
	-ffile-prefix-map=$(PS2SDK)=/ps2sdk
EE_GAME_CFLAGS = $(EE_CFLAGS) -include src/hybrid/boundary.h
EE_INCS += -Isrc -I$(ENGINE)/src -I$(HALO)/cseries -I$(HALO)/memory -I$(HALO)/tag_files -I$(HALO)/math
EE_LIBS = -ldraw -lgraph -ldma -lpacket2 -ldebug -lkernel
EE_DVP = dvp-as

.PHONY: all
all: $(EE_BIN)

$(EE_OBJS): tools/ee-hybrid.mk src/hybrid/boundary.h src/hybrid/protocol.h src/hybrid/replay.h
-include $(EE_OBJS:.o=.d)

$(HYBRID_OUTPUT)/boundary.o: src/hybrid/boundary.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_GAME_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/data.o: $(HALO)/memory/data.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_GAME_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/integer_math.o: $(HALO)/math/integer_math.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_GAME_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/core.o: src/hybrid/core.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_GAME_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/replay.o: src/hybrid/replay.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_GAME_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/main.o: src/hybrid/ee_main.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/video.o: $(ENGINE)/src/platform/video.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/chain.o: $(ENGINE)/src/render/chain.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/upload.o: $(ENGINE)/src/render/upload.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(HYBRID_OUTPUT)/world.o: src/platform/triangle.vsm
	@mkdir -p $(@D)
	$(EE_DVP) $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
