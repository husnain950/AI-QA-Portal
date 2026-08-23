FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN groupadd --system crx && useradd --system --gid crx --home-dir /app crx

# Keep the `backend` package name so imports stay stable.
COPY apps/api/backend /app/backend
COPY packages/acts_ingest /app/acts_ingest

RUN mkdir -p /app/data/uploads \
      /data/corpus/ordinance /data/corpus/acts /data/corpus/rules \
      /seed/corpus/ordinance /seed/corpus/acts /seed/corpus/rules \
    && chown -R crx:crx /app /data /seed

# Bake pipeline corpus into the image for auto-seeding on first boot.
# data/seed/ is a local build artifact (gitignored); when absent the COPY
# below is a harmless no-op (copies only the .gitkeep placeholder).
COPY data/seed/ /seed/corpus/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONOPTIMIZE=2
ENV DATABASE_URL=postgresql+psycopg://crx:crx@postgres:5432/crx
ENV STORAGE_BACKEND=s3
ENV UPLOAD_DIR=/app/data/uploads
# One per corpus in backend.services.corpus_registry.CORPORA. A lane missing here
# reports as "not mounted on this host" no matter what is actually in the volume.
ENV CORPUS_ORDINANCE=/data/corpus/ordinance
ENV CORPUS_ACTS=/data/corpus/acts
ENV CORPUS_RULES=/data/corpus/rules
ENV SEED_CORPUS_ORDINANCE=/seed/corpus/ordinance
ENV SEED_CORPUS_ACTS=/seed/corpus/acts
ENV SEED_CORPUS_RULES=/seed/corpus/rules

EXPOSE 8000

USER crx

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "50"]
