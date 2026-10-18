PYTHON ?= python3
BUILD_ENV ?= native
OFFLINE ?= 0
export BUILD_ENV OFFLINE

.PHONY: doctor bootstrap test-host toolchain-plan toolchain host-tools probe convert elf test-emulator iso
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

test-host:
	$(PYTHON) -B -m unittest discover -s tests -v
	$(PYTHON) tools/test_host.py

probe convert elf test-emulator iso:
	@echo "Target '$@' is unavailable: source acquisition and audited implementation are pending. See docs/milestones.md." >&2
	@exit 2
