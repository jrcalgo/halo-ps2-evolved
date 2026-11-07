# Invoke with the same PS2DEV/PS2SDK as the frozen production build.
PROBE_OUTPUT ?= build/opl-qualification/probe-1
PROBE_LEVEL ?= 1
ENGINE = submodules/halo-ps2/engine
EE_BIN = $(PROBE_OUTPUT)/HPS2_000.01
EE_OBJS = $(PROBE_OUTPUT)/main.o $(PROBE_OUTPUT)/diag.o $(PROBE_OUTPUT)/entry.o
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror -G0 -ffunction-sections -fdata-sections -MMD -MP \
 -DHALO_PS2_BOOT_DIAG=1 -DHCU_OPL_PROBE_LEVEL=$(PROBE_LEVEL) -DHALO_FILE_USE_FILEXIO
EE_INCS = -Isrc -I$(ENGINE)/src
EE_LDFLAGS = -Wl,-e,hcu_boot_entry -Wl,--wrap,_libcglue_init -Wl,--gc-sections -Wl,-Map,$(PROBE_OUTPUT)/probe.map
EE_LIBS = -ldebug -leedebug -lfileXio -lpatches
ifeq ($(PROBE_LEVEL),3)
EE_OBJS += $(PROBE_OUTPUT)/storage.o $(PROBE_OUTPUT)/irx.o $(PROBE_OUTPUT)/file.o $(PROBE_OUTPUT)/sha.o
endif
-include $(EE_OBJS:.o=.d)
all: $(EE_BIN)
$(PROBE_OUTPUT)/main.o: src/probe/opl_boot.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(PROBE_OUTPUT)/diag.o: src/stream/hcu_boot_diag.c src/stream/hcu_boot_diag.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(PROBE_OUTPUT)/entry.o: src/stream/hcu_boot_entry.S
	@mkdir -p $(@D)
	$(EE_CC) -G0 -c $< -o $@
$(PROBE_OUTPUT)/storage.o: src/stream/hcu_storage_boot.c
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(PROBE_OUTPUT)/irx.o: src/stream/hcu_filexio_irx.S
	$(EE_CC) -G0 -x assembler-with-cpp -DHALO_PS2_IOMANX_IRX=\"$(PS2SDK)/iop/irx/iomanX.irx\" -DHALO_PS2_FILEXIO_IRX=\"$(PS2SDK)/iop/irx/fileXio.irx\" -c $< -o $@
$(PROBE_OUTPUT)/file.o: $(ENGINE)/src/stream/file.c
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(PROBE_OUTPUT)/sha.o: src/stream/sha256.c
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
