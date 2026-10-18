EE_BIN = $(PLATFORM_OUTPUT)/platform.elf
EE_OBJS = $(PLATFORM_OUTPUT)/main.o $(PLATFORM_OUTPUT)/video.o
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror -G0
EE_INCS += -Isubmodules/halo-ps2/engine/src -Isrc
EE_LIBS = -ldraw -lgraph -ldma -lpacket2

.PHONY: all
all: $(EE_BIN)

$(PLATFORM_OUTPUT)/main.o: src/platform/main.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PLATFORM_OUTPUT)/video.o: submodules/halo-ps2/engine/src/platform/video.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
