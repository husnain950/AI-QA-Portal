#!/usr/bin/env python3
"""Gate converted corpora on severe tree-count outliers among sibling editions.

This check is corpus-level by design.  A per-document invariant cannot know that
one Sales Tax edition has 9 parsed sections while its siblings have roughly 140.
The committed discovery census supplies only identity (lane, source basename,
document group); every count used here is measured from ``output/*.json``.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from corpus_paths import LABELS, REPO_ROOT, output_dir
from legal_contract import CHILD_KINDS

SIGNATURES = REPO_ROOT / "tools" / "discovery" / "signatures.json"
DOCUMENT_ROOTS = (("chapters", "chapter"), ("schedules", "schedule"))

# A comparison needs five peers.  Below that, one unusual edition can define the
# "normal" shape, so the group is deliberately not judged.
MIN_PEERS = 5

# Flag only a collapse of more than half, and only when at least 75% of the
# other editions form a cluster within +/-25% of their own median.  The first
# condition demands a severe relative loss; the second keeps heterogeneous
# filing groups (for example, Finance Acts of very different sizes) quiet.
COLLAPSE_RATIO = 0.5
PEER_BAND = 0.25
MIN_CLUSTER_SHARE = 0.75


class QualityInputError(ValueError):
    """A signatures file or output tree cannot be interpreted safely."""


@dataclass(frozen=True)
class TreeCounts:
    """Counts taken from the JSON tree, never from ``metadata.*_count``."""

    instruments: int
    chapters: int
    parts: int
    divisions: int
    sections: int
    schedules: int
    schedule_sections: int


@dataclass(frozen=True)
class Edition:
    lane: str
    group: str
    family: str
    filename: str
    json_path: Path
    counts: TreeCounts


@dataclass(frozen=True)
class Outlier:
    edition: Edition
    peer_median: float
    clustered_peers: int
    peer_count: int


def _basename_key(value: str) -> str:
    """Cross-platform, Unicode-stable key for source and metadata basenames."""
    basename = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return unicodedata.normalize("NFC", basename).casefold()


def _group_label(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def _signature_groups(
    path: Path, lane: str
) -> dict[str, frozenset[tuple[str, str]]]:
    """Normalised source basename -> possible committed (group, family) pairs.

    Multiple signatures with the same basename are safe only when they agree on
    both fields.  Cross-group basename collisions remain explicit and are
    rejected if an output tries to use one; guessing would contaminate sibling
    sets.  Family keeps an amending instrument filed under a consolidated
    statute's folder from being mistaken for a collapsed edition of that statute.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise QualityInputError(f"cannot read signatures {path}: {err}") from err

    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise QualityInputError(f"{path}: records must be a list")

    groups: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    for position, record in enumerate(records):
        if not isinstance(record, dict) or record.get("lane") != lane:
            continue
        signature = record.get("signature")
        assignment = record.get("assignment")
        source = signature.get("path") if isinstance(signature, dict) else None
        group = signature.get("group") if isinstance(signature, dict) else None
        family = assignment.get("family") if isinstance(assignment, dict) else None
        if not isinstance(source, str) or not _basename_key(source):
            raise QualityInputError(
                f"{path}: {lane} record {position} has no source path"
            )
        if not isinstance(group, str) or not _group_label(group):
            raise QualityInputError(
                f"{path}: {lane} record {position} has no document group"
            )
        if not isinstance(family, str) or not family.strip():
            raise QualityInputError(
                f"{path}: {lane} record {position} has no assigned family"
            )
        groups[_basename_key(source)].add((_group_label(group), family.strip()))
    return {key: frozenset(values) for key, values in groups.items()}


def _walk_counts(node: dict, kind: str, counts: collections.Counter) -> None:
    if not isinstance(node, dict):
        raise QualityInputError(f"{kind} node is not an object")
    counts[kind] += 1
    for collection, child_kind in CHILD_KINDS:
        children = node.get(collection)
        if children is None:
            continue
        if not isinstance(children, list):
            raise QualityInputError(f"{kind}.{collection} is not a list")
        for child in children:
            _walk_counts(child, child_kind, counts)


def _iter_document_roots(doc: dict):
    """Yield roots from contract-v1 and instrument-shaped output."""
    for instrument in doc.get("instruments") or []:
        for collection, kind in DOCUMENT_ROOTS:
            for node in instrument.get(collection) or []:
                yield kind, node
    for collection, kind in DOCUMENT_ROOTS:
        for node in doc.get(collection) or []:
            yield kind, node


def tree_counts(doc: dict) -> TreeCounts:
    """Count the contract tree, including instrument-shaped compilations."""
    if not isinstance(doc, dict):
        raise QualityInputError("document root is not an object")
    for collection in ("instruments", "chapters", "schedules"):
        value = doc.get(collection)
        if value is not None and not isinstance(value, list):
            raise QualityInputError(f"document.{collection} is not a list")

    instruments = doc.get("instruments") or []
    if any(not isinstance(instrument, dict) for instrument in instruments):
        raise QualityInputError("instrument node is not an object")

    chapter_counts: collections.Counter = collections.Counter()
    schedule_counts: collections.Counter = collections.Counter()
    for kind, node in _iter_document_roots(doc):
        target = chapter_counts if kind == "chapter" else schedule_counts
        _walk_counts(node, kind, target)

    return TreeCounts(
        instruments=len(instruments),
        chapters=chapter_counts["chapter"],
        parts=chapter_counts["part"] + schedule_counts["part"],
        divisions=chapter_counts["division"] + schedule_counts["division"],
        sections=chapter_counts["section"],
        schedules=schedule_counts["schedule"],
        schedule_sections=schedule_counts["section"],
    )


def build_group_index(
    lane: str, paths: Sequence[Path], signatures_path: Path = SIGNATURES
) -> tuple[dict[tuple[str, str], list[Edition]], list[str]]:
    """Join converted trees to committed groups without ambiguous fallbacks."""
    source_groups = _signature_groups(signatures_path, lane)
    by_group: dict[tuple[str, str], list[Edition]] = collections.defaultdict(list)
    issues: list[str] = []
    seen: dict[str, Path] = {}

    for path in sorted(paths):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            issues.append(f"{path.name}: cannot read JSON: {err}")
            continue
        metadata = doc.get("metadata") if isinstance(doc, dict) else None
        filename = metadata.get("filename") if isinstance(metadata, dict) else None
        if not isinstance(filename, str) or not _basename_key(filename):
            issues.append(f"{path.name}: metadata.filename is missing")
            continue

        key = _basename_key(filename)
        candidates = source_groups.get(key, frozenset())
        if not candidates:
            issues.append(
                f"{path.name}: metadata.filename {filename!r} has no "
                f"committed {lane} discovery signature"
            )
            continue
        if len(candidates) != 1:
            issues.append(
                f"{path.name}: metadata.filename {filename!r} is ambiguous across "
                f"cohorts {sorted(candidates)!r}"
            )
            continue
        if key in seen:
            issues.append(
                f"{path.name}: metadata.filename {filename!r} duplicates "
                f"{seen[key].name}"
            )
            continue
        seen[key] = path

        try:
            counts = tree_counts(doc)
        except QualityInputError as err:
            issues.append(f"{path.name}: invalid output tree: {err}")
            continue
        group, family = next(iter(candidates))
        by_group[(group, family)].append(
            Edition(lane, group, family, filename, path, counts)
        )

    return dict(by_group), issues


def find_outliers(groups: Mapping[str, Sequence[Edition]]) -> list[Outlier]:
    """Find severe low section-count outliers against clustered sibling peers."""
    found: list[Outlier] = []
    for editions in groups.values():
        if len(editions) < MIN_PEERS + 1:
            continue
        for edition in editions:
            peers = [other.counts.sections for other in editions if other is not edition]
            baseline = float(statistics.median(peers))
            if baseline <= 0 or edition.counts.sections >= baseline * COLLAPSE_RATIO:
                continue
            lo, hi = baseline * (1 - PEER_BAND), baseline * (1 + PEER_BAND)
            clustered = sum(lo <= count <= hi for count in peers)
            if clustered / len(peers) >= MIN_CLUSTER_SHARE:
                found.append(Outlier(edition, baseline, clustered, len(peers)))
    return found


def _format_counts(counts: TreeCounts) -> str:
    return (
        f"instruments={counts.instruments}, chapters={counts.chapters}, "
        f"parts={counts.parts}, divisions={counts.divisions}, "
        f"sections={counts.sections}, schedules={counts.schedules}, "
        f"schedule_sections={counts.schedule_sections}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lane", choices=LABELS)
    parser.add_argument("--output", type=Path, help="override the lane output directory")
    parser.add_argument(
        "--signatures", type=Path, default=SIGNATURES,
        help="committed discovery signatures (default: tools/discovery/signatures.json)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output or output_dir(args.lane)
    paths = sorted(output.glob("*.json"))
    if not paths:
        print(f"SKIP cross-edition quality {args.lane}: no converted output under {output}")
        return 0

    try:
        groups, issues = build_group_index(args.lane, paths, args.signatures)
    except QualityInputError as err:
        print(f"FAIL cross-edition quality {args.lane}: {err}")
        print("RESULT: FAIL")
        return 1

    outliers = find_outliers(groups)
    for issue in issues:
        print(f"FAIL cross-edition join {args.lane}: {issue}")
    for outlier in outliers:
        edition = outlier.edition
        print(
            f"FAIL cross-edition sections {args.lane}/{edition.group}: "
            f"{edition.filename!r} ({edition.family}) has "
            f"{edition.counts.sections}, peer median "
            f"{outlier.peer_median:g}; {outlier.clustered_peers}/"
            f"{outlier.peer_count} peers are within +/-{PEER_BAND:.0%} "
            f"({_format_counts(edition.counts)})"
        )

    if issues or outliers:
        print(
            f"RESULT: FAIL | join issues {len(issues)} | "
            f"section outliers {len(outliers)}"
        )
        return 1

    eligible = sum(len(editions) >= MIN_PEERS + 1 for editions in groups.values())
    joined = sum(len(editions) for editions in groups.values())
    print(
        f"OK cross-edition quality {args.lane}: {joined} document(s), "
        f"{eligible} sibling group(s) compared"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
