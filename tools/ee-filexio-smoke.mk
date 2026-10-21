SMOKE_OUTPUT ?= build/ee-filexio-smoke
EE_BIN = $(SMOKE_OUTPUT)/filexio-reset-smoke.elf
EE_OBJS = $(SMOKE_OUTPUT)/main.o $(SMOKE_OUTPUT)/hcu_filexio_irx.o
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror -G0 \
	-DHALO_PS2_IOMANX_IRX=\"$(PS2SDK)/iop/irx/iomanX.irx\" \
	-DHALO_PS2_FILEXIO_IRX=\"$(PS2SDK)/iop/irx/fileXio.irx\"
EE_INCS = -I$(PS2SDK)/ee/rpc/filexio/include
EE_LIBS = -ldebug -lfileXio -lpatches

.PHONY: all clean
all: $(EE_BIN)

$(SMOKE_OUTPUT)/main.o: tests/fixtures/ee_filexio_reset_smoke.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(SMOKE_OUTPUT)/hcu_filexio_irx.o: src/stream/hcu_filexio_irx.S
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) -c $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
