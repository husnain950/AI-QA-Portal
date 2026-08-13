FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Keep the `backend` package name so imports stay stable.
COPY apps/api/backend /app/backend

RUN mkdir -p /app/data/db /app/data/uploads /data/corpus/ordinance /data/corpus/acts /seed/corpus

# Bake pipeline output JSONs into the image for auto-seeding on first boot.
# These live at /seed/corpus/ (read-only, inside image) — separate from
# /app/data/ (persistent volume mount point) so volumes don't shadow them.
# If data/seed/ doesn't exist yet the COPY is a no-op (uses a dot-ignore trick).
COPY data/seed/ordinance/ /seed/corpus/ordinance/
COPY data/seed/acts/ /seed/corpus/acts/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONOPTIMIZE=2
ENV DATABASE_PATH=/app/data/db/qa_portal.db
ENV UPLOAD_DIR=/app/data/uploads
ENV CORPUS_ORDINANCE=/data/corpus/ordinance
ENV CORPUS_ACTS=/data/corpus/acts
ENV SEED_CORPUS_ORDINANCE=/seed/corpus/ordinance
ENV SEED_CORPUS_ACTS=/seed/corpus/acts

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "50"]
