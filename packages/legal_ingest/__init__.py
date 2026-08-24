"""legal_ingest -- deterministic PDF -> structured-JSON pipeline for FBR legal texts.

One pipeline, one profile per corpus. See :mod:`legal_ingest.profiles`.
"""

from .pipeline import run
from .profiles import ACTS, RULES, Profile

__all__ = ["run", "Profile", "ACTS", "RULES"]
