.PHONY: test test-unit test-integration test-all

fmt:
	uv run ruff format .

lint:
	uv run ruff check . --fix

test: test-unit

test-unit:
	uv run pytest -m "not integration"

test-integration:
	forge build --root contracts
	forge build --root tests/integration/contracts
	RUN_ANVIL_INTEGRATION=1 uv run pytest -m integration

test-all:
	RUN_ANVIL_INTEGRATION=1 uv run pytest
