import React, { useState, useEffect } from 'react';
import { AlertCircle, Check, X } from 'lucide-react';

const AnnotationPopover = ({ selectionText, coords, onSave, onCancel }) => {
    const [issueDescription, setIssueDescription] = useState('');
    const [severity, setSeverity] = useState('error'); // 'error' | 'warning' | 'info'
    const [reviewerName, setReviewerName] = useState(
        localStorage.getItem('qa-portal-reviewer-name') || ''
    );

    useEffect(() => {
        // focus the textarea on mount
        const textarea = document.getElementById('annotation-desc-textarea');
        if (textarea) textarea.focus();
    }, []);

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
            className="annotation-popover glass-panel" 
            style={{ 
                top: coords.top, 
                left: coords.left,
                position: 'absolute'
            }}
            onClick={(e) => e.stopPropagation()} // Avoid triggering deselect in HTML panel
        >
            <div className="annotation-popover-title flex align-center gap-2">
                <AlertCircle size={16} style={{ color: 'var(--color-accent)' }} />
                <span>Report Parsing Issue</span>
            </div>

            <div style={{ fontSize: '0.75rem', fontStyle: 'italic', color: 'var(--color-text-secondary)', marginBottom: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%', borderLeft: '2px solid var(--color-accent)', paddingLeft: 6 }}>
                Selected: "{selectionText}"
            </div>

            <form onSubmit={handleSave}>
                <div className="form-group">
                    <label className="form-label">Severity</label>
                    <select 
                        className="form-select"
                        value={severity}
                        onChange={(e) => setSeverity(e.target.value)}
                    >
                        <option value="error">Critical Error</option>
                        <option value="warning">Warning / Minor mismatch</option>
                        <option value="info">Info / Formatting note</option>
                    </select>
                </div>

                <div className="form-group">
                    <label className="form-label">Description</label>
                    <textarea
                        id="annotation-desc-textarea"
                        className="form-textarea"
                        placeholder="What is wrong with this parsed HTML?"
                        value={issueDescription}
                        onChange={(e) => setIssueDescription(e.target.value)}
                        required
                    />
                </div>

                <div className="form-group">
                    <label className="form-label">Reviewer Initials</label>
                    <input
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
                        className="btn btn-secondary" 
                        style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                        onClick={onCancel}
                    >
                        <X size={14} />
                        <span>Cancel</span>
                    </button>
                    <button 
                        type="submit" 
                        className="btn btn-primary"
                        style={{ padding: '6px 12px', fontSize: '0.8rem' }}
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
