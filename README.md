# ChefLink

A comprehensive meal planning system with recipe ingestion, family meal planning, and chef operations management.

## Setup

1. Clone the repository and navigate to the project directory:
```bash
cd cheflink
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy the environment variables:
```bash
cp .env.example .env
```

5. Update the `.env` file with your configuration:
- Database credentials
- Telegram bot token
- LLM API keys (OpenAI or Anthropic)
- Google API credentials for nutrition search

6. Initialize the database:
```bash
alembic upgrade head
```

7. Run the development server:
```bash
uvicorn app.main:app --reload
```

## Development

### Code Quality
```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy .
```

### Testing
```bash
pytest
```

## Project Structure
```
cheflink/
├── app/
│   ├── api/          # API endpoints
│   ├── core/         # Core configurations and schemas
│   ├── database/     # Database models and sessions
│   ├── services/     # Business logic services
│   └── utils/        # Utility functions
├── tests/            # Test files
├── scripts/          # Utility scripts
└── docs/             # Documentation
```