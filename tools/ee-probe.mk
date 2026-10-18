EE_BIN = $(PROBE_OUTPUT)/integer-math.elf
EE_OBJS = $(PROBE_OUTPUT)/integer_math.o $(PROBE_OUTPUT)/fixture.o
EE_CFLAGS = -std=gnu11 -Wall -Wextra -Werror -G0 -include tests/gameplay_host32/prefix.h
EE_INCS += -Isubmodules/halo-64/source/cseries -Isubmodules/halo-64/source/math
EE_LIBS = -lkernel

.PHONY: all
all: $(EE_BIN)

$(PROBE_OUTPUT)/integer_math.o: submodules/halo-64/source/math/integer_math.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(PROBE_OUTPUT)/fixture.o: tests/gameplay_host32/integer_math.c
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
