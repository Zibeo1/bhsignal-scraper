.PHONY: install test run compose-up compose-down

install:
	python3 -m pip install '.[test]'

test:
	pytest

run:
	uvicorn app.main:app --reload --port 8081

compose-up:
	docker compose up --build

compose-down:
	docker compose down
