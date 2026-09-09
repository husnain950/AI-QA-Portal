import copy

import pytest

from legal_contract import represent_compilation, stamp_document
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
