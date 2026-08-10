"""Shared disposition vocabulary for annotations and findings.

Mirrors Acts_fbr anomalies.md: an anomaly faithful to a defective PDF is
recorded as source_defect with evidence, not dropped.

Used by both human annotations and detector findings so ownership of a fix
is expressible the same way in the portal and the pipeline ledger.
"""

from __future__ import annotations

# open          — not yet classified
# parse_bug     — portal/pipeline output is wrong; fix the parser
# source_defect — PDF itself is wrong; parse is faithful; lawyer must be told
# deliberate    — intentional divergence (known policy)
# not_a_defect  — false positive / dismissed
DISPOSITIONS = frozenset(
    {"open", "parse_bug", "source_defect", "deliberate", "not_a_defect"}
)

DEFAULT_DISPOSITION = "open"

# Findings queue triage. Operational state of the work item.
# new / fixed are queue lifecycle; the four ownership values are terminal
# triage outcomes that mirror DISPOSITIONS (minus open).
FINDING_TRIAGE = frozenset(
    {
        "new",
        "parse_bug",
        "source_defect",
        "deliberate",
        "not_a_defect",
        "fixed",
    }
)

# Triage values that mean a human has classified ownership (not new/fixed).
FINDING_OWNED = frozenset(DISPOSITIONS - {"open"})


def normalize_disposition(value: str | None) -> str:
    raw = (value or DEFAULT_DISPOSITION).strip().lower().replace("-", "_")
    if raw not in DISPOSITIONS:
        raise ValueError(
            f"invalid disposition {value!r}; expected one of {sorted(DISPOSITIONS)}"
        )
    return raw


def normalize_finding_triage(value: str | None) -> str:
    raw = (value or "new").strip().lower().replace("-", "_")
    if raw == "accepted":
        raw = "parse_bug"
    elif raw == "dismissed":
        raw = "not_a_defect"
    if raw not in FINDING_TRIAGE:
        raise ValueError(
            f"invalid finding triage {value!r}; expected one of {sorted(FINDING_TRIAGE)}"
        )
    return raw
