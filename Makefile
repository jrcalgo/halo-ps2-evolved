PYTHON ?= python3
BUILD_ENV ?= native
OFFLINE ?= 0
export BUILD_ENV OFFLINE

.PHONY: doctor bootstrap test-host test-gameplay-host32 host-abi32 toolchain-plan toolchain host-tools native-prerequisites smoke-elf vu-smoke probe platform-elf convert elf test-emulator iso
doctor:
	$(PYTHON) tools/doctor.py

bootstrap:
	$(PYTHON) tools/bootstrap.py

toolchain-plan:
	$(PYTHON) tools/toolchain_plan.py

toolchain:
	$(PYTHON) tools/build_toolchain.py

host-tools:
	$(PYTHON) tools/build_toolchain.py --host-tools

native-prerequisites:
	$(PYTHON) tools/host_prerequisites.py

host-abi32:
	$(PYTHON) tools/host_abi32.py

test-gameplay-host32:
	$(PYTHON) tools/test_gameplay_host32.py

smoke-elf:
	$(PYTHON) tools/build_smoke.py

vu-smoke:
	$(PYTHON) tools/build_smoke.py --vu

test-host:
	$(PYTHON) tools/test_host.py

probe:
	$(PYTHON) tools/build_probe.py

platform-elf:
	$(PYTHON) tools/build_platform.py

convert elf test-emulator iso:
	@echo "Target '$@' is unavailable: source acquisition and audited implementation are pending. See docs/milestones.md." >&2
	@exit 2
