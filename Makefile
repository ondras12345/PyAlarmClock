.PHONY: test test_hardware lint bandit

all: test lint bandit  # test_hardware needs to be started manually

test:
	python3 -m unittest discover -s tests/unit

test_hardware:
	python3 -m unittest discover -s tests/integration

lint:
	-flake8 --exclude .git,__pycache__,venv
	-mypy PyAlarmClock/__init__.py tests/unit/test_*.py tests/integration/test_*.py Examples/*.py

bandit:
	-bandit -r PyAlarmClock/ tests/ Examples/
