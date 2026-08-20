"""The sanitizer must strip anything executable without altering the legal text.

Uploaded and model-generated HTML reaches the reviewer's browser, so this is the
boundary that stops a corpus JSON from carrying a script. It is also the boundary most
likely to damage a statute by accident, hence the fidelity flags.
"""

from backend.services.html_sanitizer import (
    SANITIZER_VERSION,
    sanitize_html,
    structure_signature,
    visible_text,
)


def test_script_content_is_removed_entirely_not_unwrapped():
    result = sanitize_html('<p>Tax is due.<script>alert(1)</script></p>')
    assert result.html == "<p>Tax is due.</p>"
    assert "alert" not in result.html
    assert result.changed
    assert "dropped_tag:script" in result.diagnostics


def test_style_blocks_and_comments_go_too():
    result = sanitize_html("<p>a<style>p{}</style><!-- note -->b</p>")
    assert result.html == "<p>ab</p>"
    assert "dropped_tag:style" in result.diagnostics
    assert "dropped_comment" in result.diagnostics


def test_event_handlers_and_urls_are_dropped():
    result = sanitize_html(
        '<p onclick="steal()" onmouseover="x">Section 4</p>'
    )
    assert result.html == "<p>Section 4</p>"
    assert "dropped_attr:p.onclick" in result.diagnostics

    linked = sanitize_html('<span href="javascript:alert(1)">cite</span>')
    assert "javascript:" not in linked.html
    assert "dropped_attr:span.href" in linked.diagnostics


def test_media_and_frames_cannot_survive():
    for markup in (
        '<img src="x" onerror="alert(1)">',
        '<iframe src="//evil"></iframe>',
        '<svg><script>alert(1)</script></svg>',
        '<object data="x"></object>',
    ):
        result = sanitize_html(f"<p>text{markup}</p>")
        assert result.html == "<p>text</p>", markup


def test_legal_markup_survives_untouched():
    source = (
        '<p class="subsection">(1) Subject to <span class="cite">section 5</span>, '
        'the tax<sup class="footnote-marker" data-ref="7">7</sup> is due.</p>'
        '<table class="fbr-table"><thead><tr><th scope="col" colspan="2">Rate</th></tr></thead>'
        "<tbody><tr><td>0%</td><td>Nil</td></tr></tbody></table>"
        '<ol start="3"><li value="3">first</li></ol><br><hr>'
    )
    result = sanitize_html(source)
    assert not result.changed, result.diagnostics
    assert result.text_fidelity and result.structure_fidelity


def test_a_sanitized_fragment_keeps_its_text_and_table_shape():
    source = (
        '<div style="text-align:center;font-weight:bold" data-x="1">'
        '<table><tr><td rowspan="2">A</td><td>B</td></tr></table></div>'
    )
    result = sanitize_html(source)
    assert result.changed
    assert result.text_fidelity, "no visible character may be added or lost"
    assert result.structure_fidelity, "colspan/rowspan carry legal meaning"
    assert 'class="crx-align-center crx-bold"' in result.html, "style becomes a class"
    assert "dropped_attr:div.data-x" in result.diagnostics


def test_fidelity_flags_report_a_table_the_parser_could_not_keep():
    # A <table> nested inside a dropped container loses its structure; the flag is what
    # tells the caller to refuse the content rather than store it silently damaged.
    result = sanitize_html("<svg><table><tr><td>1</td></tr></table></svg>")
    assert result.html == ""
    assert result.structure_fidelity is False


def test_entities_and_unknown_tags_keep_their_text():
    result = sanitize_html("<marquee>Rs.&nbsp;1,000 &amp; more</marquee>")
    assert result.html == "Rs.&nbsp;1,000 &amp; more"
    assert "unwrapped_tag:marquee" in result.diagnostics
    assert result.text_fidelity


def test_visible_text_ignores_markup_and_dropped_containers():
    assert visible_text("<p>a<b>b</b></p>") == "ab"
    assert visible_text("<p>a<script>evil()</script>b</p>") == "ab"


def test_structure_signature_notices_a_changed_span():
    one = structure_signature('<table><tr><td colspan="2">x</td></tr></table>')
    two = structure_signature('<table><tr><td colspan="3">x</td></tr></table>')
    assert one != two


def test_empty_input_is_not_a_change():
    for value in ("", None):
        result = sanitize_html(value)
        assert result.html == ""
        assert not result.changed


def test_version_is_recorded_so_stored_content_can_be_re_sanitized():
    assert SANITIZER_VERSION
