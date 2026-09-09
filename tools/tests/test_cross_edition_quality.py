"""Corpus-free locks for the cross-edition tree-count gate."""

from __future__ import annotations

import json

import check_cross_edition_quality as quality


def _write_corpus(tmp_path, groups):
    output = tmp_path / "output"
    output.mkdir()
    records = []
    for group, section_counts in groups.items():
        for position, count in enumerate(section_counts):
            filename = f"{group} edition {position}.pdf"
            records.append({
                "lane": "acts",
                "signature": {"path": f"{group}/{filename}", "group": group},
            })
            doc = {
                # Deliberately wrong: the gate must count the tree, not trust
                # the parser's metadata counter.
                "metadata": {"filename": filename, "sections_count": 999},
                "chapters": [{
                    "code": "CHAPTER I",
                    "sections": [
                        {"code": str(number), "plain_text": "text"}
                        for number in range(count)
                    ],
                }],
                "schedules": [],
            }
            (output / f"doc-{len(records)}.json").write_text(
                json.dumps(doc), encoding="utf-8"
            )
    signatures = tmp_path / "signatures.json"
    signatures.write_text(json.dumps({"records": records}), encoding="utf-8")
    return output, signatures


def _run(output, signatures):
    return quality.main([
        "acts", "--output", str(output), "--signatures", str(signatures),
    ])


def test_gate_fails_deliberately_on_nine_sections_against_clustered_siblings(
        tmp_path, capsys):
    output, signatures = _write_corpus(tmp_path, {
        "Sales Tax Act": [9, 110, 125, 138, 140, 145, 151],
    })

    assert _run(output, signatures) == 1
    report = capsys.readouterr().out
    assert "FAIL cross-edition sections acts/Sales Tax Act" in report
    assert "has 9, peer median 139" in report
    assert "6/6 peers are within +/-25%" in report
    assert "sections=9" in report
    assert "999" not in report
    assert "RESULT: FAIL" in report


def test_gate_passes_normal_small_and_heterogeneous_groups(tmp_path, capsys):
    output, signatures = _write_corpus(tmp_path, {
        "Normal editions": [110, 120, 130, 140, 145, 150],
        # Five documents have too few peers for a defensible comparison.
        "Small group": [1, 1, 1, 1, 100],
        # No absolute minimum: low counts can be a normal tree shape.
        "Small trees": [1, 1, 2, 2, 2, 3],
        # A broad filing group has no peer cluster and must stay quiet.
        "Different instruments": [4, 8, 15, 31, 63, 127],
    })

    assert _run(output, signatures) == 0
    report = capsys.readouterr().out
    assert "OK cross-edition quality acts: 23 document(s)" in report
    assert "3 sibling group(s) compared" in report


def test_join_normalises_paths_case_and_unicode(tmp_path, capsys):
    output = tmp_path / "output"
    output.mkdir()
    (output / "edition.json").write_text(json.dumps({
        "metadata": {"filename": "nested/E\u0301DITION.PDF"},
        "chapters": [],
        "schedules": [],
    }), encoding="utf-8")
    signatures = tmp_path / "signatures.json"
    signatures.write_text(json.dumps({"records": [{
        "lane": "acts",
        "signature": {"path": "Group/Édition.pdf", "group": "Group"},
    }]}), encoding="utf-8")

    assert _run(output, signatures) == 0
    assert "1 document(s)" in capsys.readouterr().out


def test_join_rejects_cross_group_basename_ambiguity(tmp_path, capsys):
    output = tmp_path / "output"
    output.mkdir()
    (output / "same.json").write_text(json.dumps({
        "metadata": {"filename": "same.pdf"},
        "chapters": [],
        "schedules": [],
    }), encoding="utf-8")
    signatures = tmp_path / "signatures.json"
    signatures.write_text(json.dumps({"records": [
        {
            "lane": "acts",
            "signature": {"path": "Group A/same.pdf", "group": "Group A"},
        },
        {
            "lane": "acts",
            "signature": {"path": "Group B/same.pdf", "group": "Group B"},
        },
    ]}), encoding="utf-8")

    assert _run(output, signatures) == 1
    report = capsys.readouterr().out
    assert "ambiguous across groups ['Group A', 'Group B']" in report
    assert "section outliers 0" in report


def test_gate_skips_before_reading_signatures_when_no_corpus(tmp_path, capsys):
    output = tmp_path / "empty-output"
    output.mkdir()

    assert quality.main([
        "acts",
        "--output",
        str(output),
        "--signatures",
        str(tmp_path / "does-not-exist.json"),
    ]) == 0
    assert capsys.readouterr().out.startswith("SKIP cross-edition quality acts:")


def test_tree_counts_instrument_shaped_documents():
    doc = {
        "metadata": {"sections_count": 999},
        "instruments": [{
            "code": "Instrument 1",
            "chapters": [{
                "code": "CHAPTER I",
                "parts": [{
                    "code": "PART I",
                    "divisions": [{
                        "code": "Division I",
                        "sections": [
                            {"code": "1", "plain_text": "one"},
                            {"code": "2", "plain_text": "two"},
                        ],
                    }],
                }],
            }],
            "schedules": [{
                "code": "SCHEDULE",
                "sections": [{"code": "A", "plain_text": "schedule text"}],
            }],
        }],
    }

    assert quality.tree_counts(doc) == quality.TreeCounts(
        instruments=1,
        chapters=1,
        parts=1,
        divisions=1,
        sections=2,
        schedules=1,
        schedule_sections=1,
    )
