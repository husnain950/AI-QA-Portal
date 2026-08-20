import asyncio
import os

from backend.database import init_db
from backend.services import blob_store

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BACKEND_DIR, "uploads"))
_BOOTSTRAP_DONE = False


async def bootstrap_runtime() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    _BOOTSTRAP_DONE = True

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    await init_db()
    # Boot is deliberately read-only beyond schema migration. Corpus seeding, blob
    # conversion, provenance derivation, and variant rebuilding are explicit jobs.
    await asyncio.to_thread(blob_store.get_storage().ready)
