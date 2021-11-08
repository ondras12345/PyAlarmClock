all: test lint bandit

.PHONY: test lint bandit

test:
	python3 -m unittest

lint:
	-flake8 --exclude .git,__pycache__,venv
	-mypy PyAlarmClock/__init__.py test/test_*.py Examples/*.py

bandit:
	-bandit -r PyAlarmClock/ test/ Examples/
