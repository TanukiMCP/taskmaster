# Dockerfile - Optimized for Smithery Deployment
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for potential native extensions
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create state directory for session management
RUN mkdir -p taskmaster/state && \
    chmod 755 taskmaster/state

# Set environment variables for Smithery deployment
ENV SMITHERY_DEPLOY=true
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Expose port (will be overridden by $PORT environment variable)
EXPOSE 8080

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

# Start the server with proper signal handling
CMD ["python", "server.py"] 