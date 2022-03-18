.PHONY: all
all: test lint bandit  # test_hardware needs to be started manually

.PHONY: help
help:           ## Show this help.
	@grep -F -h "##" $(MAKEFILE_LIST) | sed -e '/unique_BhwaDzu7C/d;s/\\$$//;s/##//'

.PHONY: test
test:           ## Run unit tests.
	python3 -m unittest discover -s tests/unit

.PHONY: test_hardware
test_hardware:  ## Run integration tests that require hardware to be connected.
	python3 -m unittest discover -s tests/integration

.PHONY: lint
lint:           ## Run various linters.
	-flake8
	-mypy src/PyAlarmClock/*.py tests/unit/test_*.py tests/integration/test_*.py src/examples/*.py

.PHONY: bandit
bandit:         ## Run the bandit security linter.
	-bandit -r src/ tests/
