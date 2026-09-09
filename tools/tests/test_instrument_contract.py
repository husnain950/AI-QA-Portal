import copy
from types import SimpleNamespace

import pytest

from legal_contract import represent_compilation, stamp_document
from legal_ingest.pipeline import (
    _automatic_instrument_partitions,
    _drop_embedded_contents_blocks,
    _toc_needs_body_discovery,
)
from suite.invariants._common import inv_contract_complete
from suite.invariants.rules import inv_section_codes_ordered
from suite.loader import iter_all_leaves


def _chapter(code, section_code, page):
    return {
        "code": code,
        "heading": "General",
        "parts": [],
        "divisions": [],
        "sections": [
            {
                "code": section_code,
                "heading": f"Rule {section_code}",
                "html": f"<p>rule {section_code}</p>",
                "plain_text": f"rule {section_code}",
                "start_page": page,
                "end_page": page,
                "page_number": page,
                "footnotes": [],
            }
        ],
    }


def _assembled_document():
    return {
        "metadata": {
            "filename": "compilation.pdf",
            "total_pages": 20,
            "chapters_count": 2,
            "schedules_count": 0,
            "sections_count": 2,
        },
        "chapters": [
            _chapter("CHAPTER I", "9", 2),
            _chapter("CHAPTER I", "1", 12),
        ],
        "schedules": [],
    }


def test_compilation_hook_stamps_stable_instrument_scoped_identity():
    document = _assembled_document()
    original_chapters = list(document["chapters"])

    represent_compilation(
        document,
        [
            {
                "code": "S.R.O. 570(I)/98",
                "heading": "Passenger's Baggage (Import) Rules",
                "chapter_indexes": [0],
            },
            {
                "code": "S.R.O. 3(I)/70",
                "heading": "Frustrated Cargo Export Rules",
                "chapter_indexes": [1],
            },
        ],
    )
    stamp_document(document)

    assert "chapters" not in document and "schedules" not in document
    assert document["metadata"]["instruments_count"] == 2
    assert [instrument["type"] for instrument in document["instruments"]] == [
        "instrument",
        "instrument",
    ]
    assert [instrument["node_key"] for instrument in document["instruments"]] == [
        "inst:s-r-o-570-i-98",
        "inst:s-r-o-3-i-70",
    ]
    assert document["instruments"][0]["chapters"][0] is original_chapters[0]
    assert [leaf["node_key"] for leaf in iter_all_leaves(document)] == [
        "inst:s-r-o-570-i-98/ch:i/s:9",
        "inst:s-r-o-3-i-70/ch:i/s:1",
    ]
    assert inv_contract_complete(document) == []
    # A code restart is valid at an instrument boundary.
    assert inv_section_codes_ordered(document) == []


def test_compilation_hook_refuses_root_loss_and_overlap():
    document = _assembled_document()
    with pytest.raises(ValueError, match="do not conserve roots"):
        represent_compilation(
            copy.deepcopy(document),
            [{"code": "SRO 1", "chapter_indexes": [0]}],
        )
    with pytest.raises(ValueError, match="assigned more than once"):
        represent_compilation(
            copy.deepcopy(document),
            [
                {"code": "SRO 1", "chapter_indexes": [0]},
                {"code": "SRO 2", "chapter_indexes": [0, 1]},
            ],
        )


def _ref(text):
    return SimpleNamespace(line=SimpleNamespace(text=lambda: text))


def test_embedded_contents_rows_are_removed_but_real_rules_remain():
    refs = [
        _ref("ELECTRONIC FILING OF FEDERAL EXCISE RETURN RULES, 2005"),
        _ref("CONTENTS"),
        _ref("1. Short title, application and commencement."),
        _ref("2. Definitions."),
        _ref("3. Digital certification from NIFT."),
        _ref("------"),
        _ref("Notification No. S.R.O. 1185(I)/2005"),
        _ref("1. Short title, application and commencement. -- (1) These rules..."),
        _ref("2. Definitions. -- (1) Unless there is anything repugnant..."),
    ]

    kept, removed = _drop_embedded_contents_blocks(refs)

    assert removed == 5
    assert [ref.line.text() for ref in kept] == [
        "ELECTRONIC FILING OF FEDERAL EXCISE RETURN RULES, 2005",
        "Notification No. S.R.O. 1185(I)/2005",
        "1. Short title, application and commencement. -- (1) These rules...",
        "2. Definitions. -- (1) Unless there is anything repugnant...",
    ]


def test_contents_word_without_bounded_row_block_is_preserved():
    refs = [
        _ref("CONTENTS"),
        _ref("1. A single numbered paragraph in operative text."),
        _ref("This provision has no contents separator."),
    ]
    kept, removed = _drop_embedded_contents_blocks(refs)
    assert removed == 0
    assert kept == refs


def test_secondary_rules_root_becomes_a_separate_instrument():
    document = {
        "metadata": {
            "filename": "Federal Excise Rules 2005.pdf",
            "notified_by": "S.R.O. 534(I)/2005",
        },
        "chapters": [
            _chapter("CHAPTER I", "1", 5),
            _chapter("CHAPTER XVI", "86", 72),
            {
                **_chapter("", "1", 75),
                "heading": "ELECTRONIC FILING OF FEDERAL EXCISE RETURN RULES, 2005",
            },
        ],
        "schedules": [],
    }

    partitions = _automatic_instrument_partitions(document)

    assert partitions == [
        {
            "code": "S.R.O. 534(I)/2005",
            "heading": "Federal Excise Rules 2005.pdf",
            "chapter_indexes": [0, 1],
            "schedule_indexes": [],
        },
        {
            "code": "ELECTRONIC FILING OF FEDERAL EXCISE RETURN RULES, 2005",
            "heading": "ELECTRONIC FILING OF FEDERAL EXCISE RETURN RULES, 2005",
            "chapter_indexes": [2],
            "schedule_indexes": [],
        },
    ]


def test_customs_chapter_index_memorandum_uses_body_discovery():
    assert _toc_needs_body_discovery(
        [
            "Chapter   Contents-                  Page No.",
            "I. Definitions 300",
            "MEMORANDUM",
            "S.No. Subject Old Notification No. Rules No. Page No.",
        ]
    )
    assert not _toc_needs_body_discovery(
        ["Chapter Contents Page No.", "I. Definitions 5"]
    )
