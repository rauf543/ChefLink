.PHONY: help install dev-install test lint format run-api run-bot migrate docker-up docker-down clean

help:
	@echo "Available commands:"
	@echo "  install       Install production dependencies"
	@echo "  dev-install   Install development dependencies"
	@echo "  test          Run tests"
	@echo "  lint          Run linting"
	@echo "  format        Format code"
	@echo "  run-api       Run the API server"
	@echo "  run-bot       Run the Telegram bot"
	@echo "  migrate       Run database migrations"
	@echo "  docker-up     Start all services with Docker"
	@echo "  docker-down   Stop all Docker services"
	@echo "  clean         Clean up generated files"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pre-commit install

test:
	pytest -v

lint:
	ruff check .
	mypy .

format:
	black .
	ruff check --fix .

run-api:
	uvicorn app.main:app --reload

run-bot:
	python bot.py

migrate:
	alembic upgrade head

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +