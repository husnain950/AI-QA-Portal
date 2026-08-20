import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Check, AlertCircle } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';
import { sanitizeLegalHtml } from '../../utils/sanitizeHtml';

const FootnoteText = ({ footnote, annotations, onSelect }) => {
    const textRef = React.useRef(null);

    const handleMouseUp = () => {
        const selection = window.getSelection();
        if (!selection.rangeCount || selection.isCollapsed) return;

        const range = selection.getRangeAt(0);
        const container = textRef.current;
        if (!container || !container.contains(range.commonAncestorContainer)) return;

        const text = selection.toString().trim();
        if (!text) return;

        // Calculate offsets
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(container);
        preCaretRange.setEnd(range.startContainer, range.startOffset);
        const start = preCaretRange.toString().length;
        const end = start + range.toString().length;

        // Position popover relative to selection
        const rect = range.getBoundingClientRect();
        const htmlPanelBody = container.closest('.panel-body');
        if (!htmlPanelBody) return;
        const panelRect = htmlPanelBody.getBoundingClientRect();

        const coords = {
            top: rect.bottom - panelRect.top + htmlPanelBody.scrollTop + 8,
            left: rect.left - panelRect.left + htmlPanelBody.scrollLeft + (rect.width / 2) - 160
        };

        if (onSelect) {
            onSelect(footnote.id, text, start, end, coords);
        }
    };

    // If we have HTML content (with tables), render it directly
    if (footnote.html_content) {
        return (
            <div
                ref={textRef}
                className="footnote-text footnote-html-content"
                onMouseUp={handleMouseUp}
                dangerouslySetInnerHTML={{ __html: sanitizeLegalHtml(footnote.html_content) }}
            />
        );
    }

    const fnAnnots = annotations ? annotations.filter(a => a.footnote_id === footnote.id && a.status === 'open') : [];
    if (fnAnnots.length === 0) {
        return (
            <div ref={textRef} className="footnote-text" onMouseUp={handleMouseUp}>
                {footnote.text}
            </div>
        );
    }

    const sortedAnnots = [...fnAnnots].sort((a, b) => a.start_offset - b.start_offset);
    const parts = [];
    let currentIdx = 0;
    const text = footnote.text;

    sortedAnnots.forEach((annot) => {
        if (annot.start_offset >= currentIdx && annot.end_offset <= text.length) {
            if (annot.start_offset > currentIdx) {
                parts.push(text.slice(currentIdx, annot.start_offset));
            }
            parts.push(
                <mark
                    key={annot.id}
                    className="qa-highlight"
                    data-annotation-id={annot.id}
                    data-severity={annot.severity}
                    title={`Issue: ${annot.issue_description || 'No description'}`}
                    style={{ cursor: 'pointer' }}
                >
                    {text.slice(annot.start_offset, annot.end_offset)}
                </mark>
            );
            currentIdx = annot.end_offset;
        }
    });

    if (currentIdx < text.length) {
        parts.push(text.slice(currentIdx));
    }

    return (
        <div ref={textRef} className="footnote-text" onMouseUp={handleMouseUp}>
            {parts.map((p, idx) => <React.Fragment key={idx}>{p}</React.Fragment>)}
        </div>
    );
};

const FootnotePanel = ({ footnotes, annotations, onFootnoteSelect }) => {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const { updateFootnoteStatus, setCurrentPage } = useReviewStore();

    if (!footnotes || footnotes.length === 0) return null;

    const handlePageClick = (page, e) => {
        e.preventDefault();
        if (page) {
            setCurrentPage(page);
        }
    };

    const listId = 'footnotes-panel-list';

    return (
        <div className="footnotes-panel surface-panel">
            <div className="footnotes-header">
                <h3 className="footnotes-title">
                    Footnotes ({footnotes.length})
                </h3>
                <button
                    className="btn btn-ghost btn-icon footnotes-toggle"
                    aria-expanded={!isCollapsed}
                    aria-controls={listId}
                    aria-label={isCollapsed ? 'Expand footnotes' : 'Collapse footnotes'}
                    onClick={(e) => {
                        e.stopPropagation();
                        setIsCollapsed(!isCollapsed);
                    }}
                >
                    {isCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                </button>
            </div>

            {!isCollapsed && (
                <div className="footnotes-list" id={listId}>
                    {footnotes.map((fn) => (
                        <div
                            key={fn.id}
                            className={`footnote-card ${fn.review_status === 'approved' ? 'approved' : fn.review_status === 'has_issues' ? 'flagged' : ''}`}
                        >
                            <div className="footnote-meta">
                                <span className="footnote-marker">Marker: {fn.marker}</span>
                                {fn.page && (
                                    <button
                                        className="footnote-page-jump"
                                        onClick={(e) => handlePageClick(fn.page, e)}
                                        title={`Jump PDF to page ${fn.page}`}
                                    >
                                        PDF Page {fn.page}
                                    </button>
                                )}
                            </div>

                            <FootnoteText
                                footnote={fn}
                                annotations={annotations}
                                onSelect={onFootnoteSelect}
                            />

                            <div className="footnote-actions">
                                <button
                                    className={`btn btn-xs ${fn.review_status === 'approved' ? 'review-status-approved' : 'btn-secondary'}`}
                                    onClick={() => updateFootnoteStatus(fn.id, fn.review_status === 'approved' ? 'pending' : 'approved')}
                                >
                                    <Check size={12} />
                                    <span>{fn.review_status === 'approved' ? 'Approved' : 'Approve'}</span>
                                </button>
                                <button
                                    className={`btn btn-xs ${fn.review_status === 'has_issues' ? 'review-status-flagged' : 'btn-secondary'}`}
                                    onClick={() => updateFootnoteStatus(fn.id, fn.review_status === 'has_issues' ? 'pending' : 'has_issues')}
                                >
                                    <AlertCircle size={12} />
                                    <span>{fn.review_status === 'has_issues' ? 'Flagged' : 'Flag Issue'}</span>
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default FootnotePanel;
