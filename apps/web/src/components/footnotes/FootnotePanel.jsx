import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Check, AlertCircle } from 'lucide-react';
import { useReviewStore } from '../../stores/reviewStore';

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
                dangerouslySetInnerHTML={{ __html: footnote.html_content }}
                style={{ '--font-mono': "'Fira Code', 'Cascadia Code', 'Courier New', monospace" }}
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

    return (
        <div className="footnotes-panel glass-panel" style={{ background: 'var(--color-bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)' }}>
            <div 
                className="footnotes-header" 
                onClick={() => setIsCollapsed(!isCollapsed)}
            >
                <h3 className="flex align-center gap-2" style={{ fontSize: '0.95rem', fontWeight: 700 }}>
                    Footnotes ({footnotes.length})
                </h3>
                <button className="btn btn-secondary btn-icon" style={{ border: 'none', height: 24, width: 24 }}>
                    {isCollapsed ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
            </div>

            {!isCollapsed && (
                <div className="footnotes-list">
                    {footnotes.map((fn) => (
                        <div 
                            key={fn.id} 
                            className={`footnote-card ${fn.review_status === 'approved' ? 'approved' : fn.review_status === 'has_issues' ? 'flagged' : ''}`}
                        >
                            <div className="footnote-meta">
                                <span className="footnote-marker">Marker: {fn.marker}</span>
                                {fn.page && (
                                    <button 
                                        className="btn" 
                                        onClick={(e) => handlePageClick(fn.page, e)}
                                        style={{ 
                                            background: 'var(--color-accent-light)', 
                                            color: 'var(--color-accent)', 
                                            fontSize: '0.75rem', 
                                            padding: '2px 8px',
                                            fontWeight: 700,
                                            border: 'none',
                                            cursor: 'pointer',
                                            borderRadius: 'var(--radius-sm)'
                                        }}
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

                            <div className="flex gap-2" style={{ marginTop: 8, justifyContent: 'flex-end' }}>
                                <button
                                    className={`btn ${fn.review_status === 'approved' ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ 
                                        padding: '4px 10px', 
                                        fontSize: '0.75rem',
                                        backgroundColor: fn.review_status === 'approved' ? 'var(--color-success)' : 'transparent',
                                        color: fn.review_status === 'approved' ? '#ffffff' : 'var(--color-text-secondary)',
                                        borderColor: fn.review_status === 'approved' ? 'var(--color-success)' : 'var(--color-border)',
                                    }}
                                    onClick={() => updateFootnoteStatus(fn.id, fn.review_status === 'approved' ? 'pending' : 'approved')}
                                >
                                    <Check size={12} />
                                    <span>{fn.review_status === 'approved' ? 'Approved' : 'Approve'}</span>
                                </button>
                                <button
                                    className={`btn ${fn.review_status === 'has_issues' ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ 
                                        padding: '4px 10px', 
                                        fontSize: '0.75rem',
                                        backgroundColor: fn.review_status === 'has_issues' ? 'var(--color-error)' : 'transparent',
                                        color: fn.review_status === 'has_issues' ? '#ffffff' : 'var(--color-text-secondary)',
                                        borderColor: fn.review_status === 'has_issues' ? 'var(--color-error)' : 'var(--color-border)',
                                    }}
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
