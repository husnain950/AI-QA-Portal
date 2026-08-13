import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import { AlertCircle, Check, X } from 'lucide-react';

const AnnotationPopover = ({ selectionText, coords, onSave, onCancel }) => {
    const rootRef = useRef(null);
    const textareaRef = useRef(null);
    const [issueDescription, setIssueDescription] = useState('');
    const [severity, setSeverity] = useState('error'); // 'error' | 'warning' | 'info'
    const [reviewerName, setReviewerName] = useState(
        localStorage.getItem('qa-portal-reviewer-name') || ''
    );
    const [clampedLeft, setClampedLeft] = useState(null);

    useEffect(() => {
        textareaRef.current?.focus();
    }, []);

    // Escape cancels the annotation.
    useEffect(() => {
        const onKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onCancel();
            }
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onCancel]);

    // Clamp within the positioned ancestor so the form never renders off-screen.
    useLayoutEffect(() => {
        const el = rootRef.current;
        if (!el || !coords) return;
        const parent = el.offsetParent;
        if (!parent) return;
        const margin = 8;
        const maxLeft = parent.clientWidth - el.offsetWidth - margin;
        const next = Math.max(margin, Math.min(coords.left, Math.max(margin, maxLeft)));
        if (next !== coords.left) setClampedLeft(next);
    }, [coords]);

    const handleSave = (e) => {
        e.preventDefault();
        if (!issueDescription.trim()) return;

        // Save reviewer name in localStorage for convenience
        if (reviewerName.trim()) {
            localStorage.setItem('qa-portal-reviewer-name', reviewerName.trim());
        }

        onSave({
            issueDescription: issueDescription.trim(),
            severity,
            reviewerName: reviewerName.trim() || 'QA Reviewer'
        });
    };

    if (!coords) return null;

    return (
        <div
            ref={rootRef}
            className="annotation-popover surface-panel"
            role="dialog"
            aria-label="Report parsing issue"
            style={{
                top: coords.top,
                left: clampedLeft ?? coords.left,
                position: 'absolute'
            }}
            onClick={(e) => e.stopPropagation()} // Avoid triggering deselect in HTML panel
        >
            <div className="annotation-popover-title flex align-center gap-2">
                <AlertCircle size={16} style={{ color: 'var(--color-accent)' }} />
                <span>Report parsing issue</span>
            </div>

            <div className="annotation-popover-quote" title={selectionText}>
                Selected: "{selectionText}"
            </div>

            <form onSubmit={handleSave}>
                <div className="form-group">
                    <label className="form-label" htmlFor="annotation-severity">Severity</label>
                    <select
                        id="annotation-severity"
                        className="form-select"
                        value={severity}
                        onChange={(e) => setSeverity(e.target.value)}
                    >
                        <option value="error">Critical error</option>
                        <option value="warning">Warning / minor mismatch</option>
                        <option value="info">Info / formatting note</option>
                    </select>
                </div>

                <div className="form-group">
                    <label className="form-label" htmlFor="annotation-desc-textarea">Description</label>
                    <textarea
                        id="annotation-desc-textarea"
                        ref={textareaRef}
                        className="form-textarea"
                        placeholder="What is wrong with this parsed HTML?"
                        value={issueDescription}
                        onChange={(e) => setIssueDescription(e.target.value)}
                        required
                    />
                </div>

                <div className="form-group">
                    <label className="form-label" htmlFor="annotation-reviewer">Reviewer initials</label>
                    <input
                        id="annotation-reviewer"
                        type="text"
                        className="form-input"
                        placeholder="e.g. QA-1"
                        value={reviewerName}
                        onChange={(e) => setReviewerName(e.target.value)}
                    />
                </div>

                <div className="form-actions">
                    <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={onCancel}
                        title="Cancel (Esc)"
                    >
                        <X size={14} />
                        <span>Cancel</span>
                    </button>
                    <button
                        type="submit"
                        className="btn btn-sm btn-primary"
                        disabled={!issueDescription.trim()}
                    >
                        <Check size={14} />
                        <span>Save</span>
                    </button>
                </div>
            </form>
        </div>
    );
};

export default AnnotationPopover;
