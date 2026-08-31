"""The output contract every ingest package emits, in one place.

`data/corpora/<lane>/output/*.json` is the boundary between the pipeline and the
portal, and until now it was a convention rather than a contract: two parsers
emitted two different shapes, and nothing in a file recorded which parser wrote
it. `docs/pipeline-contract.md` states the contract; this module is the part of
it that is code, so both pipelines stamp it the same way rather than each
growing its own copy.

Three concerns, deliberately split by who knows the answer:

``CONTRACT_VERSION`` and ``stamp_identity``
    what the PARSER emits. A parser knows the shape it produces, so it stamps
    these itself.

``stamp_run_provenance``
    what the RUN was -- lane, parser revision, wall-clock. A `run()` does not
    know which lane invoked it or what revision it is; `tools/convert.py` does,
    and it is the only writer. Calling `run()` directly (the suites, a test)
    therefore yields no provenance, which is correct: there was no conversion.

Nothing here parses. It is pure dict manipulation over an assembled result, so
it has no pipeline dependency in either direction and both packages can import
it without importing each other.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
from pathlib import Path

#: Bumped only when a consumer that reads the previous version would be wrong.
#: Adding an optional key is not a bump; changing or removing one is.
CONTRACT_VERSION = 1

#: Node type -> the abbreviation used in ``node_key``.
KEY_ABBREV = {"chapter": "ch", "part": "pt", "division": "dv",
              "schedule": "sch", "section": "s"}

#: Where a child list sits in the tree, and what a node in it IS. This is the
#: convention the output has always followed positionally; stamping it makes a
#: consumer stop having to infer a node's kind from which keys happen to exist.
CHILD_KINDS = (("parts", "part"), ("divisions", "division"), ("sections", "section"))


def slug(code: str, kind: str) -> str:
    """``"CHAPTER XIV-A"`` -> ``"xiv-a"``; ``"114A"`` -> ``"114a"``.

    An empty code is the synthetic root a flat act gets (the 20 Finance Acts and
    the single gazette Acts have no containers at all, so ``run`` makes one to
    parent their clauses). It is named as synthetic rather than given a position,
    because a position is exactly the kind of identity ``node_key`` exists to
    avoid depending on.
    """
    text = re.sub(rf"^\s*{kind}\b[\s\-]*", "", code.strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", "-", text.strip()).lower() or "~root"


def stamp_identity(nodes, kind: str, prefix: str = "") -> None:
    """Give every node its ``type`` and its ``node_key``, in place.

    Two additive keys, on containers and leaves alike:

    ``type``      what the node IS. ``toc.Node.kind`` has always computed this
                  and ``_node_to_dict`` has always thrown it away, so the output
                  used one dict shape for a chapter, a schedule part and a
                  section leaf and left a consumer to tell them apart by which
                  keys happened to be present.

    ``node_key``  the ancestor chain BY CODE -- ``ch:vii/pt:i/s:114`` -- not by
                  array index. It sits beside the ``source_key`` that
                  ``json_parser._stable_id`` mints (``/chapters/0/sections/3``),
                  and what it buys is that a node inserted above a leaf no longer
                  renames every leaf below it. Sibling codes that repeat get an
                  ordinal, so the key is unique within its parent -- and,
                  measured over the whole corpus, within its document.
    """
    seen: dict[str, int] = {}
    for node in nodes:
        code = slug(node.get("code") or "", kind)
        seen[code] = seen.get(code, 0) + 1
        if seen[code] > 1:
            code = f"{code}~{seen[code]}"
        node["type"] = kind
        node["node_key"] = f"{prefix}{KEY_ABBREV.get(kind, kind)}:{code}"
        for key, child_kind in CHILD_KINDS:
            if node.get(key):
                stamp_identity(node[key], child_kind, node["node_key"] + "/")


def stamp_document(result: dict) -> dict:
    """Stamp the whole assembled result: identity on every node, and the version.

    Both pipelines call this at the same point -- once ``chapters`` and
    ``schedules`` are assembled and before the preamble and the footnote-adoption
    passes, neither of which adds or removes a node.
    """
    stamp_identity(result.get("chapters") or [], "chapter")
    stamp_identity(result.get("schedules") or [], "schedule")
    result.setdefault("metadata", {})["contract_version"] = CONTRACT_VERSION
    return result


def pipeline_revision(root: Path | None = None) -> str:
    """The git revision that produced a conversion, or ``"unknown"``.

    Never raises and never blocks: a corpus converted from a tarball, a Docker
    image with no ``.git``, or a machine with no git on PATH all yield
    ``"unknown"`` rather than failing a conversion over provenance. A dirty tree
    is marked, because "which parser wrote this" is the question the field
    exists to answer and a dirty tree cannot answer it.
    """
    root = root or Path(__file__).resolve().parent.parent
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if not head:
        return "unknown"
    return f"{head}-dirty" if dirty else head


def stamp_run_provenance(result: dict, lane: str, *, revision: str | None = None) -> dict:
    """Record which conversion produced this file: lane, revision, wall-clock.

    Without these, a corpus at two parser revisions is indistinguishable from a
    corpus at one -- which is not hypothetical: 85 of 103 documents were
    re-converted on 2026-08-30 and nothing on disk said so, so the committed
    anomaly register silently stopped describing the corpus it was measured from.
    """
    metadata = result.setdefault("metadata", {})
    metadata["lane"] = lane
    metadata["pipeline_revision"] = revision if revision is not None else pipeline_revision()
    metadata["converted_at"] = (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    ).replace("+00:00", "Z")
    return result


#: Metadata keys the contract requires of every document, whatever the lane.
REQUIRED_METADATA = (
    "contract_version", "filename", "total_pages",
    "chapters_count", "schedules_count", "sections_count",
)

#: Metadata keys a *converted* document additionally carries. Absent when a
#: caller drove ``run()`` directly, which is why these are checked separately.
REQUIRED_RUN_METADATA = ("lane", "pipeline_revision", "converted_at")


def _demo() -> None:
    # ---- identity: by code, not by position ------------------------------
    tree = [{"code": "CHAPTER VII", "parts": [
        {"code": "PART I", "divisions": [], "parts": [],
         "sections": [{"code": "114"}, {"code": "114"}]}],
        "divisions": [], "sections": []}]
    stamp_identity(tree, "chapter")
    assert tree[0]["type"] == "chapter" and tree[0]["node_key"] == "ch:vii"
    assert tree[0]["parts"][0]["node_key"] == "ch:vii/pt:i"
    # a repeated sibling code still resolves, and still does not use an index
    assert [s["node_key"] for s in tree[0]["parts"][0]["sections"]] == \
           ["ch:vii/pt:i/s:114", "ch:vii/pt:i/s:114~2"]

    # the synthetic root a flat act gets is named as synthetic, not positioned
    root = [{"code": "", "parts": [], "divisions": [], "sections": [{"code": "1"}]}]
    stamp_identity(root, "chapter")
    assert root[0]["node_key"] == "ch:~root"
    assert slug("CHAPTER XIV-A", "chapter") == "xiv-a"
    assert slug("114A", "section") == "114a"

    # ---- the property the portal depends on ------------------------------
    # Inserting a node ABOVE a leaf must not rename the leaf. This is the whole
    # reason the key exists, so it is asserted rather than described.
    before = [{"code": "I", "parts": [], "divisions": [],
               "sections": [{"code": "2"}, {"code": "3"}]}]
    stamp_identity(before, "chapter")
    was = [s["node_key"] for s in before[0]["sections"]]
    after = [{"code": "I", "parts": [], "divisions": [],
              "sections": [{"code": "1"}, {"code": "2"}, {"code": "3"}]}]
    stamp_identity(after, "chapter")
    now = [s["node_key"] for s in after[0]["sections"]]
    assert was == ["ch:i/s:2", "ch:i/s:3"], was
    assert now[1:] == was, (now, was)          # the two survivors keep their keys
    assert now[0] == "ch:i/s:1"                # only the new leaf is new

    # ---- whole-document stamping -----------------------------------------
    doc = {"metadata": {"filename": "x.pdf"},
           "chapters": [{"code": "I", "parts": [], "divisions": [], "sections": []}],
           "schedules": [{"code": "FIRST SCHEDULE", "parts": [], "divisions": [],
                          "sections": []}]}
    stamp_document(doc)
    assert doc["metadata"]["contract_version"] == CONTRACT_VERSION
    assert doc["chapters"][0]["node_key"] == "ch:i"
    assert doc["schedules"][0]["type"] == "schedule"
    # "FIRST SCHEDULE" keeps the word: the prefix strip only removes a LEADING
    # kind word, so "Schedule II" -> "sch:ii" but "FIRST SCHEDULE" -> the whole
    # phrase. Asserted against what the corpus actually holds (sch:first-schedule
    # x33, sch:the-first-schedule x27), not against what reads tidier.
    assert doc["schedules"][0]["node_key"] == "sch:first-schedule"
    assert slug("Schedule II", "schedule") == "ii"

    stamp_run_provenance(doc, "acts", revision="deadbeef")
    assert doc["metadata"]["lane"] == "acts"
    assert doc["metadata"]["pipeline_revision"] == "deadbeef"
    assert doc["metadata"]["converted_at"].endswith("Z")
    assert all(k in doc["metadata"] for k in REQUIRED_RUN_METADATA)

    # A real revision is a hex sha, "unknown", or either marked dirty -- never a
    # traceback, whatever the tree looks like.
    assert re.fullmatch(r"(unknown|[0-9a-f]{7,40})(-dirty)?", pipeline_revision())

    print("legal_contract: ok")


if __name__ == "__main__":
    _demo()
