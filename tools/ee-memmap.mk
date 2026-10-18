EE_BIN = $(MEMMAP_OUTPUT)/memmap.elf
EE_OBJS = $(MEMMAP_OUTPUT)/memmap.o
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror -G0
EE_LIBS =

.PHONY: all
all: $(EE_BIN)

$(MEMMAP_OUTPUT)/memmap.o: src/platform/memmap.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
