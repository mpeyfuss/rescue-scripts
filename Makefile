# Format code
fmt:
	uv run ruff format .

# Lint code
lint:
	uv run ruff check --fix .

# Run script
rescue:
	uv run main.py