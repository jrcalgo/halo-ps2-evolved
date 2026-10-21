EE_BIN = $(SMOKE_OUTPUT)/halo-smoke.elf
EE_OBJS = $(SMOKE_OUTPUT)/main.o
EE_SMOKE_SOURCE ?= tests/fixtures/ee_smoke.c
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror
EE_LIBS = -ldebug

.PHONY: all
all: $(EE_BIN)

$(EE_OBJS): $(EE_SMOKE_SOURCE)
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
