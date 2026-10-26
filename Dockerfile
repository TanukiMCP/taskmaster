FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY taskmaster ./taskmaster
COPY design ./design
RUN pip install --no-cache-dir .

ENV TASKMASTER_STATE_DIR=/data
RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app

EXPOSE 8080
CMD ["taskmaster", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
