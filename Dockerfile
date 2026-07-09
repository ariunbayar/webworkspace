# Demo image: runs the Flask workspace app (runserver.py) with a co-located
# redis so the app's hard-coded 127.0.0.1:6379 connection works unmodified.
FROM python:3.9-slim

# redis-server + redis-cli (redis-tools) for the in-container datastore
RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

ENV FLASK_APP=runserver:app \
    REDIS_HOST=127.0.0.1 \
    DEMO_DIR=/app/static/js \
    PORT=8000

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
