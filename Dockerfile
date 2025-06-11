# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create state directory
RUN mkdir -p taskmaster/state

# Set environment variable to indicate Smithery deployment
ENV SMITHERY_DEPLOY=true

# Expose port (will be set by $PORT environment variable)
EXPOSE 8080

# Start the server
CMD ["python", "server.py"] 