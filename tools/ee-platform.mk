EE_BIN = $(PLATFORM_OUTPUT)/platform.elf
ENGINE = submodules/halo-ps2/engine
EE_OBJS = $(PLATFORM_OUTPUT)/main.o $(PLATFORM_OUTPUT)/video.o $(PLATFORM_OUTPUT)/pad.o \
	$(PLATFORM_OUTPUT)/chain.o $(PLATFORM_OUTPUT)/upload.o \
	$(PLATFORM_OUTPUT)/world.o
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror -Wno-unused-parameter -G0 -MMD -MP \
	-ffile-prefix-map=$(PS2SDK)=/ps2sdk
EE_INCS += -I$(ENGINE)/src -Isrc
EE_LIBS = -ldraw -lgraph -ldma -lpacket2 -lpad
EE_DVP = dvp-as

.PHONY: all
all: $(EE_BIN)

$(EE_OBJS): tools/ee-platform.mk
-include $(EE_OBJS:.o=.d)

$(PLATFORM_OUTPUT)/main.o: src/platform/main.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/video.o: $(ENGINE)/src/platform/video.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/pad.o: $(ENGINE)/src/platform/pad.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/chain.o: $(ENGINE)/src/render/chain.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/upload.o: $(ENGINE)/src/render/upload.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/selftest.o: $(ENGINE)/src/render/selftest.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/world.o: src/platform/triangle.vsm
	@mkdir -p $(@D)
	$(EE_DVP) $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
