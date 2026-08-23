"""rules_ingest -- the Rules corpus reading of :mod:`legal_ingest`.

The Acts and the Rules pipelines were two verbatim forks of the same 11,500 lines.
They are one pipeline now; this is the Rules binding of it -- the corpus's profile,
applied.

Kept as a package rather than folded into its callers so that the lane entry point
stays exactly what it was: ``from rules_ingest import run``. Anything reaching for a
particular stage imports :mod:`legal_ingest` directly.
"""

from __future__ import annotations

import functools

from legal_ingest import pipeline
from legal_ingest.profiles import RULES

#: Convert one Rules PDF. Same signature as before the merge.
run = functools.partial(pipeline.run, profile=RULES)

PROFILE = RULES

__all__ = ["run", "PROFILE"]
