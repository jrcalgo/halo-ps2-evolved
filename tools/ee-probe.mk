EE_BIN = $(PROBE_OUTPUT)/integer-math.elf
EE_OBJS = $(PROBE_OUTPUT)/integer_math.o $(PROBE_OUTPUT)/fixture.o $(PROBE_OUTPUT)/main.o
PROBE_SOURCE ?= submodules/halo-64/source/math/integer_math.c
EE_CFLAGS = -std=gnu11 -DHALO_PS2=1 -fno-strict-aliasing -Wall -Wextra -Werror -G0 -MMD -MP \
	-ffile-prefix-map=$(PS2SDK)=/ps2sdk -include tests/gameplay_host32/prefix.h
EE_INCS += -Isubmodules/halo-64/source/cseries -Isubmodules/halo-64/source/math
EE_LIBS = -ldebug -lkernel

.PHONY: all
all: $(EE_BIN)

$(EE_OBJS): tools/ee-probe.mk tests/gameplay_host32/prefix.h
-include $(EE_OBJS:.o=.d)

$(PROBE_OUTPUT)/integer_math.o: $(PROBE_SOURCE)
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PROBE_OUTPUT)/fixture.o: tests/gameplay_host32/integer_math.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Dmain=halo_integer_fixture_main -c $< -o $@

$(PROBE_OUTPUT)/main.o: src/probe/main.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
