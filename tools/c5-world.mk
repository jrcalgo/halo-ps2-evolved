# C5 guest parent objects (new file). Includes the shared world makefile unchanged and adds only the C5 parent
# objects: the session, the boot harness, the bot and survival cores and their CE glue. Used by tools/c5_build.py.
# Run as: make -f tools/c5-world.mk WORLD_OUTPUT=<dir> ... parent-objects
include tools/ee-world.mk

C5_OBJS = $(WORLD_OUTPUT)/stream/hcu_c5_session.o \
	$(WORLD_OUTPUT)/stream/hcu_c5_boot.o \
	$(WORLD_OUTPUT)/stream/hcu_coop_modes.o \
	$(WORLD_OUTPUT)/stream/hcu_coop_ce_bind.o \
	$(WORLD_OUTPUT)/stream/hcu_bot.o \
	$(WORLD_OUTPUT)/stream/hcu_survival.o \
	$(WORLD_OUTPUT)/stream/hcu_survival_ce.o

.PHONY: parent-objects
parent-objects: $(C5_OBJS)

$(WORLD_OUTPUT)/stream/hcu_c5_session.o: src/stream/hcu_c5_session.c src/stream/hcu_c5_session.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

# C5_BOOT_DEFINES (set by tools/c5_build.py): -DHALO_PS2_SURVIVAL=1 and -DHCU_C5_LIFECYCLE_VARIANT=<actv index>
# (derived from the C1 roster for the boot map). Only this object takes them.
$(WORLD_OUTPUT)/stream/hcu_c5_boot.o: src/stream/hcu_c5_boot.c src/stream/hcu_c5_session.h src/stream/hcu_local_setup_rows.inc
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) $(C5_BOOT_DEFINES) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_coop_modes.o: src/stream/hcu_coop_modes.c src/stream/hcu_coop_modes.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_coop_ce_bind.o: src/stream/hcu_coop_ce_bind.c src/stream/hcu_coop_ce_bind.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bot.o: src/stream/hcu_bot.c src/stream/hcu_bot.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_survival.o: src/stream/hcu_survival.c src/stream/hcu_survival.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_survival_ce.o: src/stream/hcu_survival_ce.c src/stream/hcu_survival_ce.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

# C5 measurement only: admit the diagnostic map list in hcu_map_service.c for the C5 build. Set by tools/c5_build.py
# (--map-capacity-diagnostic) and applied to this one object. The shared ee-world.mk rule and default builds never see it.
ifeq ($(C5_MAP_CAPACITY_DIAGNOSTIC),1)
$(WORLD_OUTPUT)/stream/hcu_map_service.o: EE_CFLAGS += -DHALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC=1
endif
