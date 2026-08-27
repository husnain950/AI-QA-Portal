import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, ChevronDown, ChevronUp, Check, AlertCircle } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';
import { sanitizeLegalHtml } from '../../utils/sanitizeHtml';
import { getSelectionCharacterOffsetsWithin, highlightFromOffsets } from '../../hooks/useTextSelection';

const JUMP_HIGHLIGHT_MS = 1600;

const FootnoteText = ({ footnote, annotations, onSelect }) => {
    const textRef = React.useRef(null);

    const handleMouseUp = () => {
        const selection = window.getSelection();
        if (!selection.rangeCount || selection.isCollapsed) return;

        const range = selection.getRangeAt(0);
        const container = textRef.current;
        if (!container || !container.contains(range.commonAncestorContainer)) return;

        const { start, end } = getSelectionCharacterOffsetsWithin(container);
        const highlight = highlightFromOffsets(container, start, end);
        if (!highlight) return;

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
            onSelect(footnote.id, highlight.text, highlight.start, highlight.end, coords);
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
    const [flashId, setFlashId] = useState(null);
    const cardRefs = useRef(new Map());
    const {
        updateFootnoteStatus,
        setCurrentPage,
        activeFootnoteId,
        jumpToCite,
        footnoteJumpNonce,
    } = useReviewStore();

    // Cite → footnote: expand when a jump is requested
    useEffect(() => {
        if (!activeFootnoteId || !footnoteJumpNonce) return;
        setIsCollapsed(false);
    }, [activeFootnoteId, footnoteJumpNonce]);

    // Scroll/flash only on cite → footnote (footnoteJumpNonce), not on up-arrow jumps
    useEffect(() => {
        if (!activeFootnoteId || !footnoteJumpNonce || isCollapsed) return;

        const card = cardRefs.current.get(String(activeFootnoteId));
        if (!card) return;

        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        setFlashId(activeFootnoteId);
        const timer = setTimeout(() => setFlashId(null), JUMP_HIGHLIGHT_MS);
        return () => clearTimeout(timer);
    }, [activeFootnoteId, isCollapsed, footnoteJumpNonce]);

    if (!footnotes || footnotes.length === 0) return null;

    const handlePageClick = (page, e) => {
        e.preventDefault();
        if (page) {
            setCurrentPage(page);
        }
    };

    const handleJumpToCite = (fn, e) => {
        e.preventDefault();
        e.stopPropagation();
        if (fn?.id != null) {
            jumpToCite(fn.id);
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
                            ref={(el) => {
                                if (el) cardRefs.current.set(String(fn.id), el);
                                else cardRefs.current.delete(String(fn.id));
                            }}
                            id={`footnote-card-${fn.id}`}
                            data-footnote-id={fn.id}
                            className={`footnote-card ${fn.review_status === 'approved' ? 'approved' : fn.review_status === 'has_issues' ? 'flagged' : ''} ${flashId === fn.id ? 'footnote-card-active' : ''}`}
                        >
                            <div className="footnote-meta">
                                <div className="footnote-marker-row">
                                    <span className="footnote-marker">Marker: {fn.marker}</span>
                                    <button
                                        type="button"
                                        className="footnote-cite-jump"
                                        onClick={(e) => handleJumpToCite(fn, e)}
                                        title="Jump back to citation in text"
                                        aria-label={`Jump back to citation for marker ${fn.marker}`}
                                    >
                                        <ArrowUp size={14} aria-hidden="true" />
                                    </button>
                                </div>
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
