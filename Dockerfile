FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (including ping capability)
RUN apt-get update && apt-get install -y \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /data
ENV DATABASE_URL=/data/latency_monitor.db

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
