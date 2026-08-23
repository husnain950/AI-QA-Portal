"""acts_ingest -- the Acts corpus reading of :mod:`legal_ingest`.

The Acts and the Rules pipelines were two verbatim forks of the same 11,500 lines.
They are one pipeline now; this is the Acts binding of it -- the corpus's profile,
applied.

Kept as a package rather than folded into its callers so that the lane entry point
stays exactly what it was: ``from acts_ingest import run``. Anything reaching for a
particular stage imports :mod:`legal_ingest` directly.
"""

from __future__ import annotations

import functools

from legal_ingest import pipeline
from legal_ingest.profiles import ACTS

#: Convert one Acts PDF. Same signature as before the merge.
run = functools.partial(pipeline.run, profile=ACTS)

PROFILE = ACTS

__all__ = ["run", "PROFILE"]
