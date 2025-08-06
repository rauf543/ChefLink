FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 cheflink && chown -R cheflink:cheflink /app
USER cheflink

# Expose port
EXPOSE 8000

# Default command for API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]