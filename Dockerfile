FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app.py auth.py cache.py registry.py audio_cache.py health.py .
COPY db/ ./db/
COPY adapters/ ./adapters/
COPY routes/ ./routes/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
COPY alembic.ini .
COPY alembic/ ./alembic/

EXPOSE 5055

CMD ["python", "-m", "scripts.bootstrap"]
