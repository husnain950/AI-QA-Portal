import json

from backend.services.json_parser import is_junk_leaf, parse_json_document
from backend.tests.conftest import sample_document


def test_source_keys_and_ids_are_stable_despite_repeated_legal_codes():
    first_sections, first_footnotes = parse_json_document(
        sample_document(),
        document_id="document-1",
    )
    second_sections, second_footnotes = parse_json_document(
        sample_document(),
        document_id="document-1",
    )

    assert [section["section_code"] for section in first_sections] == ["1", "1"]
    assert [section["source_key"] for section in first_sections] == [
        "/chapters/0/sections/0",
        "/chapters/0/sections/1",
    ]
    assert len({section["source_key"] for section in first_sections}) == 2
    assert [section["id"] for section in first_sections] == [
        section["id"] for section in second_sections
    ]
    assert [footnote["id"] for footnote in first_footnotes] == [
        footnote["id"] for footnote in second_footnotes
    ]


def test_json_pointer_escaping_handles_container_names_safely():
    payload = json.loads(sample_document())
    payload["chapters"][0]["code"] = "I/~"
    sections, _ = parse_json_document(json.dumps(payload), document_id="document-1")

    # Array position, not a legal label, defines identity.
    assert sections[0]["source_key"] == "/chapters/0/sections/0"


def test_leaf_shaped_parts_under_chapters_become_sections():
    """rvw_export emits PART leaves (plain_text, no children) under chapters."""
    payload = {
        "metadata": {"filename": "x.pdf", "total_pages": 6},
        "chapters": [
            {
                "code": "",
                "heading": "",
                "parts": [
                    {
                        "code": "PART I",
                        "heading": "Gazette continuation",
                        "page_number": 5,
                        "html": "<p>customs amendment text</p>",
                        "plain_text": "customs amendment text",
                        "start_page": 5,
                        "end_page": 6,
                        "footnotes": [],
                    }
                ],
                "divisions": [],
                "sections": [
                    {
                        "code": "1",
                        "heading": "Short title",
                        "page_number": 2,
                        "html": "<p>short title</p>",
                        "plain_text": "short title",
                        "start_page": 2,
                        "end_page": 2,
                        "footnotes": [],
                    }
                ],
            }
        ],
        "schedules": [],
        "preamble": {"html": "", "plain_text": ""},
    }
    sections, _ = parse_json_document(json.dumps(payload), document_id="document-1")
    assert sorted(s["start_page"] for s in sections) == [2, 5]
    leaf = next(s for s in sections if s["start_page"] == 5)
    assert leaf["section_code"] == "PART I"
    assert leaf["plain_text"] == "customs amendment text"
    assert leaf["source_key"] == "/chapters/0/parts/0"
    assert leaf["chapter_code"] is None
    assert leaf["chapter_heading"] is None


def test_skips_gazette_and_contents_junk_leaves_and_normalizes_headings():
    payload = {
        "metadata": {"filename": "x.pdf", "total_pages": 20},
        "chapters": [
            {
                "code": "CHAPTER I",
                "heading": "PRELIMINARY................",
                "parts": [],
                "divisions": [],
                "sections": [
                    {
                        "code": "1",
                        "heading": "Short title................",
                        "page_number": 3,
                        "html": "<p>short title</p>",
                        "plain_text": "short title",
                        "start_page": 3,
                        "end_page": 3,
                        "footnotes": [],
                    },
                    {
                        "code": "PART I",
                        "heading": "] THE GAZETTE OF PAKISTAN, EXTRA., JUNE 30, 2024",
                        "page_number": 1,
                        "html": "<p>THE GAZETTE OF PAKISTAN</p>",
                        "plain_text": "THE GAZETTE OF PAKISTAN EXTRA",
                        "start_page": 1,
                        "end_page": 1,
                        "footnotes": [],
                    },
                    {
                        "code": "CHAPTER II",
                        "heading": "Appointments Section Page No. 12",
                        "page_number": 2,
                        "html": "<p>Section Page No. 12 13 14</p>",
                        "plain_text": "Section Page No.\n3 Short title 10\n3A Directorate 11\n3AA Powers 12",
                        "start_page": 2,
                        "end_page": 2,
                        "footnotes": [],
                    },
                ],
            }
        ],
        "schedules": [],
        "preamble": {"html": "", "plain_text": ""},
    }
    sections, _ = parse_json_document(json.dumps(payload), document_id="document-1")
    assert len(sections) == 1
    assert sections[0]["section_code"] == "1"
    assert sections[0]["section_heading"] == "Short title"
    assert sections[0]["chapter_heading"] == "PRELIMINARY"


def test_normalize_heading_strips_gazette_prefix_and_toc_leaders():
    from backend.services.json_parser import normalize_heading

    assert normalize_heading(
        "] THE GAZETTE OF PAKISTAN, EXTRA., MAY 9, 2024 161 cases under clause (a)"
    ).startswith("cases under clause")
    assert (
        normalize_heading("Short title, extent and commencement. ………..7")
        == "Short title, extent and commencement"
    )
    assert normalize_heading("Definitions…………………………………………………… ..7-29 Chapter-II") == "Definitions"


def test_schedule_containers_set_hierarchy_kind_schedule():
    payload = {
        "metadata": {"filename": "x.pdf", "total_pages": 10},
        "chapters": [
            {
                "code": "CHAPTER I",
                "heading": "PRELIMINARY",
                "parts": [],
                "divisions": [],
                "sections": [
                    {
                        "code": "1",
                        "heading": "Short title",
                        "page_number": 1,
                        "html": "<p>short title</p>",
                        "plain_text": "short title",
                        "start_page": 1,
                        "end_page": 1,
                        "footnotes": [],
                    }
                ],
            }
        ],
        "schedules": [
            {
                "code": "THE FIRST SCHEDULE",
                "heading": "RATES",
                "parts": [],
                "divisions": [],
                "sections": [
                    {
                        "code": "1",
                        "heading": "Rate of tax",
                        "page_number": 8,
                        "html": "<p>rate</p>",
                        "plain_text": "rate",
                        "start_page": 8,
                        "end_page": 8,
                        "footnotes": [],
                    }
                ],
            }
        ],
        "preamble": {"html": "", "plain_text": ""},
    }
    sections, _ = parse_json_document(json.dumps(payload), document_id="document-1")
    by_key = {s["source_key"]: s for s in sections}
    assert by_key["/chapters/0/sections/0"]["hierarchy_kind"] == "chapter"
    schedule_leaf = by_key["/schedules/0/sections/0"]
    assert schedule_leaf["hierarchy_kind"] == "schedule"
    assert schedule_leaf["chapter_code"] == "THE FIRST SCHEDULE"
    assert schedule_leaf["source_key"].startswith("/schedules/")


def _leaf(code, page, text="body"):
    return {
        "code": code,
        "heading": f"Heading {code}",
        "page_number": page,
        "html": f"<p>{text}</p>",
        "plain_text": text,
        "start_page": page,
        "end_page": page,
        "footnotes": [],
    }


def test_reading_order_follows_the_page_not_the_tree():
    """Loose sections interleaved with parts must still read front to back.

    The export nests three sibling lists per container and this parser walks them
    sections -> parts -> divisions, so a statute whose loose sections interleave with
    its parts has no tree ordering that expresses its reading order. The Customs Act
    1969 walked to page 147 and then jumped back to page 8; "Section N of X" counted
    backwards with it.
    """
    payload = {
        "metadata": {"filename": "x.pdf", "total_pages": 100},
        "chapters": [
            {
                "code": "",
                "heading": "",
                "divisions": [],
                # Direct sections late in the document...
                "sections": [_leaf("88", 88), _leaf("90", 90)],
                # ...and a part that starts at the very front.
                "parts": [
                    {
                        "code": "PART I",
                        "heading": "",
                        "parts": [],
                        "divisions": [],
                        "sections": [_leaf("1", 1), _leaf("4", 40)],
                    }
                ],
            }
        ],
        "schedules": [],
        "preamble": {"html": "", "plain_text": ""},
    }
    sections, _ = parse_json_document(json.dumps(payload), document_id="doc-order")

    pages = [s["start_page"] for s in sections]
    assert pages == sorted(pages), pages
    assert pages == [1, 40, 88, 90]
    # sort_order is what the reader paginates by, so it has to agree.
    assert [s["sort_order"] for s in sections] == [0, 1, 2, 3]


def test_reading_order_is_stable_within_a_page():
    """Sub-page position is not recoverable from the export, so ties keep tree order."""
    payload = {
        "metadata": {"filename": "x.pdf", "total_pages": 10},
        "chapters": [
            {
                "code": "",
                "heading": "",
                "parts": [],
                "divisions": [],
                "sections": [_leaf("A", 5, "first"), _leaf("B", 5, "second"),
                             _leaf("C", 5, "third")],
            }
        ],
        "schedules": [],
        "preamble": {"html": "", "plain_text": ""},
    }
    sections, _ = parse_json_document(json.dumps(payload), document_id="doc-tie")
    assert [s["section_code"] for s in sections] == ["A", "B", "C"]


def test_numeric_right_hand_column_is_not_a_contents_listing():
    """A table whose right column holds section references is statute, not a TOC.

    The Customs Act §156 offences table is column-interleaved with a trailing column of
    section numbers. A "four lines, three ending in a number" heuristic classified 226
    such leaves as junk across the corpus — up to 40,000 characters of statute each —
    and dropped them before the reviewer ever saw them.
    """
    leaf = {
        "code": "CHAPTER XI",
        "heading": "65. If any goods be taken on the person-",
        "plain_text": (
            "65. If any goods be taken on the person-in-charge 130\n"
            "board any conveyance at of such conveyance\n"
            "any customs-station in shall be liable to a\n"
            "contravention of section penalty not exceeding\n"
            "130, 1[twenty five\n"
            "thousand] rupees.\n"
            "66. If any goods not specified the person-in-charge 131\n"
        ),
        "html": "<p>65. If any goods be taken…</p>",
    }
    assert not is_junk_leaf(leaf)


def test_explicit_page_no_column_is_still_a_contents_listing():
    """The reliable signal stays: an actual "Page No" column header."""
    leaf = {
        "code": "CHAPTER I",
        "heading": "",
        "plain_text": "Section Page No\n1. Short title 1\n2. Definitions 2\n",
        "html": "<p>Section Page No</p>",
    }
    assert is_junk_leaf(leaf)
