PROBE_SOURCE ?= submodules/halo-64/source/memory/data.c
EE_BIN = $(PROBE_OUTPUT)/datum.elf
EE_OBJS = $(PROBE_OUTPUT)/data.o $(PROBE_OUTPUT)/fixture.o $(PROBE_OUTPUT)/main.o
EE_CFLAGS = -std=gnu11 -DHALO_PS2=1 -fno-strict-aliasing -Wall -Wextra -Werror -Wno-multichar -G0 -MMD -MP \
	-ffile-prefix-map=$(PS2SDK)=/ps2sdk -include tests/gameplay_host32/datum_prefix.h
EE_INCS += -Isubmodules/halo-64/source/cseries -Isubmodules/halo-64/source/memory \
	-Isubmodules/halo-64/source/tag_files
EE_LIBS = -ldebug -lkernel
.PHONY: all
all: $(EE_BIN)
$(EE_OBJS): tools/ee-datum.mk tests/gameplay_host32/datum_prefix.h tests/gameplay_host32/prefix.h
-include $(EE_OBJS:.o=.d)
$(PROBE_OUTPUT)/data.o: $(PROBE_SOURCE)
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
$(PROBE_OUTPUT)/fixture.o: tests/gameplay_host32/datum.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Dmain=halo_datum_fixture_main -c $< -o $@
$(PROBE_OUTPUT)/main.o: src/probe/datum_main.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@
include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
