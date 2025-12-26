FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies with increased timeout
RUN pip install --no-cache-dir --timeout=1000 -r requirements.txt

# Copy application
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8000

# Run application with optimized settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
