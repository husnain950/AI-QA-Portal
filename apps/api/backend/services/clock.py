"""One source of "now", in the three shapes this API already emits.

There were seven definitions of it across services and routes, in three mutually
incompatible return types -- a `datetime`, an ISO string keeping `+00:00`, and the same
string with `Z` substituted -- plus a dozen sites that inlined
`datetime.now(timezone.utc)` and bypassed all of them. One of them was still on the
deprecated naive `datetime.utcnow()`.

The three shapes are kept, deliberately and separately, rather than collapsed into one:
each is already serialized into a response body or a database column, so changing which
one a given call site returns would change the API. What is removed is seven copies of
the arithmetic, not the distinction between the formats.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """An offset-aware UTC datetime, for columns and comparisons."""
    return datetime.now(timezone.utc)


def iso_now() -> str:
    """ISO 8601 keeping the ``+00:00`` offset."""
    return utc_now().isoformat()


def iso_now_z() -> str:
    """ISO 8601 with ``Z`` in place of ``+00:00``."""
    return iso_now().replace("+00:00", "Z")


def _demo() -> None:
    assert utc_now().tzinfo is timezone.utc
    assert iso_now().endswith("+00:00")
    assert iso_now_z().endswith("Z") and "+00:00" not in iso_now_z()
    # the two string forms differ only in the offset spelling, which is exactly why
    # they cannot be merged: both are already on the wire
    assert iso_now()[:19] == iso_now_z()[:19]
    print("clock self-check passed")


if __name__ == "__main__":
    _demo()
