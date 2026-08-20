# deploy/Dockerfile — single-container build for Hugging Face Spaces (free
# CPU tier, no credit card required). Runs Redis, the Celery worker, Celery
# beat, and the FastAPI app together in one container via supervisord,
# since Spaces' free tier only runs one container per Space (no
# docker-compose / multi-service support like the project's main
# Dockerfile + docker-compose.yml, which is what you'd use on a real VPS).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    redis-server \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /var/log/supervisor
COPY deploy/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Redis and the API live in the same container, so these can be hardcoded
# rather than set as Space secrets. GOOGLE_API_KEY and INTERNAL_RELOAD_TOKEN
# still need to be set as Space secrets (see deploy/README_HF_SPACES.md).
ENV REDIS_URL=redis://localhost:6379/0
ENV API_BASE_URL=http://localhost:7860

# Hugging Face Spaces expects the container to listen on port 7860.
EXPOSE 7860

CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
