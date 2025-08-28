# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps (if any later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Create data directory before dropping privileges
RUN mkdir -p /data && chmod 775 /data

COPY src ./src
COPY run.py .
COPY README.md .

# Create an unprivileged user and give ownership of /data and app directory
RUN useradd -m botuser && chown -R botuser:botuser /app /data
USER botuser

# Database and data volume (owned by botuser)
VOLUME ["/data"]
ENV BOT_DB_PATH=/data/bot.db

# Expect DISCORD_TOKEN to be provided via environment or compose file
# Insert your Discord Bot token in docker-compose.yml or .env file as DISCORD_TOKEN=YOUR_TOKEN_HERE

ENTRYPOINT ["python", "run.py"]
