from remap_pages_to_pdf import CONTENTS_MIN, WINDOW, compact, remap


def leaf(code, heading, start, end, text=""):
    return {"code": code, "heading": heading, "html": "<p/>", "plain_text": text,
            "start_page": start, "end_page": end, "page_number": start,
            "footnotes": [{"page": end}]}


def test_leaves_follow_their_headings_into_the_rendered_pages():
    # Word put these on pages 1, 2, 2 and 3; the render runs two pages long before
    # the second one and a third before the last.
    doc = {"metadata": {"total_pages": 3}, "chapters": [{"sections": [
        leaf("1", "Short title and commencement", 1, 2),
        leaf("2", "Definitions of every term", 2, 2),
        leaf("3", "", 2, 3, text="x\nno heading here but a long first line"),
        leaf("4", "Returns to be filed annually", 3, 3),
    ]}]}
    pages = [compact(t) for t in (
        "1. Short title and commencement.—", "", "",
        "2. Definitions of every term.— ... no heading here but a long first line",
        "", "4. Returns to be filed annually",
    )]
    result = remap(doc, pages)

    got = [(s["start_page"], s["end_page"]) for s in doc["chapters"][0]["sections"]]
    # A leaf that ended on its successor's first page in Word ends on it here too;
    # leaf 3 is found by its body line, on the page it shared with leaf 2 in Word.
    assert got == [(1, 4), (4, 4), (4, 6), (6, 6)], got
    assert result == {"leaves": 4, "located": 4, "contents_pages": 0}
    assert doc["metadata"]["total_pages"] == 6
    assert doc["chapters"][0]["sections"][3]["page_number"] == 6
    # A footnote moves with its leaf and stays inside it.
    assert [s["footnotes"][0]["page"] for s in doc["chapters"][0]["sections"]] == [2, 4, 5, 6]


def test_an_unfound_leaf_keeps_the_last_offset_and_never_moves_back():
    doc = {"chapters": [{"sections": [
        leaf("1", "Short title and commencement", 1, 1),
        leaf("2", "Nothing prints this heading", 2, 2),
    ]}]}
    pages = [compact(t) for t in ("", "", "1. Short title and commencement", "", "")]
    remap(doc, pages)
    assert [s["start_page"] for s in doc["chapters"][0]["sections"]] == [3, 4]


def test_an_earlier_mention_cannot_pull_a_leaf_back_above_its_predecessor():
    doc = {"chapters": [{"sections": [
        leaf("1", "Short title and commencement", 2, 2),
        leaf("2", "Definitions of every term", 2, 2),
    ]}]}
    pages = [compact(t) for t in (
        "see 1 Short title and commencement and 2 Definitions of every term",
        "1. Short title and commencement", "2. Definitions of every term",
    )]
    remap(doc, pages)
    # Page 1 and page 3 are equally near leaf 2's expected page 2; page 1 is above
    # leaf 1, so it is not a candidate at all.
    assert [s["start_page"] for s in doc["chapters"][0]["sections"]] == [2, 3]


def test_contents_pages_are_skipped_even_past_the_narrow_window():
    # Sales Tax Rules 2006 in miniature: a contents page lists every heading, and the
    # body starts further past its declared page than WINDOW reaches.
    offset = WINDOW + 1
    names = [f"Rule number {n} of the rules" for n in range(1, CONTENTS_MIN + 1)]
    doc = {"chapters": [{"sections": [
        leaf(str(n), name, n, n) for n, name in enumerate(names, 1)
    ]}]}
    body = {n + offset: f"{n}. {name}" for n, name in enumerate(names, 1)}
    pages = [compact(" ".join(f"{n} {name}" for n, name in enumerate(names, 1)))] + [
        compact(body.get(page, "")) for page in range(2, CONTENTS_MIN + offset + 1)
    ]
    result = remap(doc, pages)
    assert result["contents_pages"] == 1
    assert [s["start_page"] for s in doc["chapters"][0]["sections"]] == sorted(body)


def test_a_defaulted_page_is_placed_only_where_its_heading_prints_once():
    # Tree order: rule 1 (p20), a schedule part Word left on page 1, another on page
    # 1, then rule 2 (p21). The first part's heading prints once; the second's twice.
    doc = {"chapters": [{"sections": [
        leaf("1", "Short title and commencement", 20, 20),
        leaf("PART I", "Rates of tax for individuals", 1, 1),
        leaf("PART II", "Rates for everyone else too", 1, 1),
        leaf("2", "Definitions of every term", 21, 21),
    ]}]}
    text = {20: "1. Short title and commencement", 21: "2. Definitions of every term",
            24: "PART I Rates of tax for individuals", 25: "PART II Rates for everyone else too",
            26: "see PART II Rates for everyone else too"}
    pages = [compact(text.get(page, "")) for page in range(1, 27)]
    result = remap(doc, pages)
    got = [s["start_page"] for s in doc["chapters"][0]["sections"]]
    # The walk is undisturbed, the unique heading moves, the ambiguous one stays.
    assert got == [20, 24, 1, 21], got
    assert result["located"] == 3
