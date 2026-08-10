import React, { useRef, useEffect, useState } from 'react';
import { useTextSelection } from '../../hooks/useTextSelection';
import { useReviewStore } from '../../stores/reviewStore';
import AnnotationPopover from '../annotations/AnnotationPopover';
import FootnotePanel from '../footnotes/FootnotePanel';
import { formatQualityFlagList } from '../../utils/qualityFlags';
import { useUiStore } from '../../stores/uiStore';
import { Copy, Check, Code, Eye, AlignLeft, AlertTriangle } from 'lucide-react';

const HtmlPanel = ({ section, sectionId, htmlContent, footnotes, qualityFlags }) => {
    const qualityReasons = formatQualityFlagList(
        qualityFlags ?? section?.quality_flags,
    );
    const containerRef = useRef(null);
    const pushToast = useUiStore((s) => s.pushToast);
    const { annotations, createAnnotation, fetchAnnotations } = useReviewStore();
    const [popoverCoords, setPopoverCoords] = useState(null);
    const [selectionData, setSelectionData] = useState(null);
    const [paneMode, setPaneMode] = useState('rendered');
    const [copied, setCopied] = useState(false);
    const [hoverFootnote, setHoverFootnote] = useState(null);
    const [clickFootnote, setClickFootnote] = useState(null);

    // Fetch annotations whenever section changes
    useEffect(() => {
        if (sectionId) {
            fetchAnnotations(sectionId);
        }
    }, [sectionId, fetchAnnotations]);

    // Listen to text selections
    const { clearSelection } = useTextSelection(containerRef, (data) => {
        if (paneMode !== 'rendered') return; // Disable annotations/selection logic in raw/json modes
        setSelectionData(data);
        setPopoverCoords(data.coords);
    });

    // Inject highlighting marks into rendered DOM & Bind Tooltip Listeners
    useEffect(() => {
        const container = containerRef.current;
        if (!container || !htmlContent) return;

        // Reset DOM to clean state
        container.innerHTML = htmlContent;

        // Attach Instant Hover & Click Popups to Cite nodes
        const cites = container.querySelectorAll('.cite');
        cites.forEach((cite) => {
            const titleText = cite.getAttribute('title');
            if (titleText) {
                cite.setAttribute('data-footnote-text', titleText);
                cite.removeAttribute('title'); // Disable default slow native browser tooltip
            }
            
            const handleMouseEnter = () => {
                const text = cite.getAttribute('data-footnote-text') || '';
                const rect = cite.getBoundingClientRect();
                const containerRect = container.getBoundingClientRect();
                
                const centerOfMarker = rect.left - containerRect.left + (rect.width / 2);
                const halfPopupWidth = 150; // 140px (half of max-width 280) + 10px safety margin
                
                let boundedLeft = centerOfMarker;
                if (boundedLeft < halfPopupWidth) {
                    boundedLeft = halfPopupWidth;
                } else if (boundedLeft > containerRect.width - halfPopupWidth) {
                    boundedLeft = Math.max(halfPopupWidth, containerRect.width - halfPopupWidth);
                }
                
                setHoverFootnote({
                    text,
                    marker: cite.textContent,
                    coords: {
                        top: rect.top - containerRect.top - 8,
                        left: boundedLeft
                    }
                });
            };

            const handleMouseLeave = () => {
                setHoverFootnote(null);
            };

            const handleClick = (e) => {
                e.stopPropagation();
                e.preventDefault();
                const text = cite.getAttribute('data-footnote-text') || '';
                const rect = cite.getBoundingClientRect();
                const containerRect = container.getBoundingClientRect();
                
                const centerOfMarker = rect.left - containerRect.left + (rect.width / 2);
                const halfPopupWidth = 170; // 160px (half of max-width 320) + 10px safety margin
                
                let boundedLeft = centerOfMarker;
                if (boundedLeft < halfPopupWidth) {
                    boundedLeft = halfPopupWidth;
                } else if (boundedLeft > containerRect.width - halfPopupWidth) {
                    boundedLeft = Math.max(halfPopupWidth, containerRect.width - halfPopupWidth);
                }
                
                setClickFootnote({
                    text,
                    marker: cite.textContent,
                    coords: {
                        top: rect.bottom - containerRect.top + 8,
                        left: boundedLeft
                    }
                });
            };

            cite.addEventListener('mouseenter', handleMouseEnter);
            cite.addEventListener('mouseleave', handleMouseLeave);
            cite.addEventListener('click', handleClick);
        });

        if (!annotations || annotations.length === 0) return;

        // Inject <mark> tags for all annotations
        annotations.forEach((annot) => {
            if (annot.footnote_id) return; // Skip footnote annotations in main text container
            if (annot.status === 'resolved') return; // Skip resolved annotations
            // Stale offsets would highlight the wrong span; the Sidebar's Recheck tab
            // is where these are surfaced instead.
            if (annot.anchor_status && annot.anchor_status !== 'anchored') return;
            const range = createRangeFromOffsets(container, annot.start_offset, annot.end_offset);
            if (range) {
                const mark = document.createElement('mark');
                mark.className = 'qa-highlight';
                mark.setAttribute('data-annotation-id', annot.id);
                mark.setAttribute('data-severity', annot.severity);
                mark.setAttribute('title', `Issue: ${annot.issue_description || 'No description'}`);
                
                try {
                    range.surroundContents(mark);
                } catch {
                    // Fallback if cross-element selection
                    try {
                        const content = range.extractContents();
                        mark.appendChild(content);
                        range.insertNode(mark);
                    } catch (err) {
                        console.error('Failed to apply fallback highlight:', err);
                    }
                }
            }
        });
    }, [htmlContent, annotations]);

    // Close click footnote popup on ESC key or clicking outside
    useEffect(() => {
        if (!clickFootnote) return;

        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                setClickFootnote(null);
            }
        };

        const handleDocumentClick = (e) => {
            const popupElement = document.getElementById('footnote-click-popup');
            if (popupElement && !popupElement.contains(e.target)) {
                setClickFootnote(null);
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        const timeoutId = setTimeout(() => {
            document.addEventListener('click', handleDocumentClick);
        }, 0);

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            clearTimeout(timeoutId);
            document.removeEventListener('click', handleDocumentClick);
        };
    }, [clickFootnote]);

    const handleSaveAnnotation = async (data) => {
        if (!sectionId || !selectionData) return;
        try {
            await createAnnotation(sectionId, {
                highlightedText: selectionData.text,
                startOffset: selectionData.start,
                endOffset: selectionData.end,
                contextBefore: selectionData.contextBefore,
                contextAfter: selectionData.contextAfter,
                issueDescription: data.issueDescription,
                severity: data.severity,
                reviewerName: data.reviewerName,
                footnoteId: selectionData.footnoteId
            });
            handleCancelAnnotation();
        } catch (e) {
            pushToast({ type: 'error', message: 'Failed to save annotation: ' + e.message });
        }
    };

    const handleCancelAnnotation = () => {
        clearSelection();
        setPopoverCoords(null);
        setSelectionData(null);
        setClickFootnote(null);
    };

    const handleFootnoteSelect = (footnoteId, text, start, end, coords) => {
        setSelectionData({
            text,
            start,
            end,
            footnoteId
        });
        setPopoverCoords(coords);
    };

    const handleCopyContent = () => {
        let textToCopy = '';
        if (paneMode === 'json') {
            const sectionData = section || { id: sectionId, html_content: htmlContent, footnotes };
            textToCopy = JSON.stringify(sectionData, null, 2);
        } else if (paneMode === 'plain') {
            textToCopy = section?.plain_text || '';
        } else {
            textToCopy = htmlContent;
        }
        if (!textToCopy) return;
        
        const copyToClipboard = async (text) => {
            // 1. Try modern Clipboard API first
            if (navigator.clipboard && navigator.clipboard.writeText) {
                try {
                    await navigator.clipboard.writeText(text);
                    return; // Successfully copied
                } catch (err) {
                    console.warn('Modern clipboard API failed, trying fallback method...', err);
                }
            }
            
            // 2. Fallback using a temporary textarea
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            textarea.style.top = '0';
            textarea.setAttribute('readonly', ''); // Prevent visual keyboard on mobile
            document.body.appendChild(textarea);
            
            const activeEl = document.activeElement;
            textarea.select();
            textarea.setSelectionRange(0, 99999); // Safe selection range for iOS
            
            try {
                const successful = document.execCommand('copy');
                if (!successful) {
                    throw new Error('execCommand returned false');
                }
            } catch (err) {
                console.error('Fallback copy method failed:', err);
            } finally {
                document.body.removeChild(textarea);
                if (activeEl && typeof activeEl.focus === 'function') {
                    activeEl.focus();
                }
            }
        };

        copyToClipboard(textToCopy)
            .then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            })
            .catch((err) => {
                console.error('All copy methods failed: ', err);
            });
    };

    return (
        <div className="flex flex-col height-100" style={{ height: '100%' }} onClick={handleCancelAnnotation}>
            <div className="panel-header glass-panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', boxSizing: 'border-box' }}>
                <div className="flex flex-col">
                    <span className="panel-title">
                        {paneMode === 'rendered' && 'Parsed HTML Content'}
                        {paneMode === 'plain' && 'Extracted Plain Text'}
                        {paneMode === 'html' && 'Raw HTML Markup'}
                        {paneMode === 'json' && 'Raw Section JSON'}
                    </span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                        {paneMode === 'rendered' && 'Highlight text in this pane to report discrepancies'}
                        {paneMode === 'plain' && 'Viewing punctuation-faithful extracted text'}
                        {paneMode === 'html' && 'Viewing raw HTML markup code'}
                        {paneMode === 'json' && 'Viewing raw JSON data for this section'}
                    </span>
                </div>
                <div className="flex align-center gap-2" onClick={(e) => e.stopPropagation()}>
                    <button 
                        className={`btn ${paneMode === 'rendered' ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                        onClick={() => setPaneMode('rendered')}
                        title="Switch to Rendered HTML View"
                    >
                        <Eye size={14} />
                        <span>Rendered</span>
                    </button>
                    <button
                        className={`btn ${paneMode === 'plain' ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                        onClick={() => setPaneMode('plain')}
                        title="Switch to Plain Text View"
                    >
                        <AlignLeft size={14} />
                        <span>Plain Text</span>
                    </button>
                    <button 
                        className={`btn ${paneMode === 'html' ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                        onClick={() => setPaneMode('html')}
                        title="Switch to Raw HTML Code View"
                    >
                        <Code size={14} />
                        <span>Raw HTML</span>
                    </button>
                    <button 
                        className={`btn ${paneMode === 'json' ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                        onClick={() => setPaneMode('json')}
                        title="Switch to Raw JSON View"
                    >
                        <Code size={14} />
                        <span>Raw JSON</span>
                    </button>
                    <button 
                        className="btn btn-secondary"
                        style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                        onClick={handleCopyContent}
                        title={`Copy ${paneMode === 'json' ? 'JSON' : paneMode === 'plain' ? 'plain text' : 'HTML'} to clipboard`}
                    >
                        {copied ? <Check size={14} style={{ color: 'var(--color-success)' }} /> : <Copy size={14} />}
                        <span>
                            {copied
                                ? 'Copied!'
                                : paneMode === 'json'
                                    ? 'Copy JSON'
                                    : paneMode === 'plain'
                                        ? 'Copy Text'
                                        : 'Copy HTML'}
                        </span>
                    </button>
                </div>
            </div>

            <div className="panel-body" style={{ position: 'relative' }}>
                {qualityReasons.length > 0 && (
                    <div
                        className="quality-flags-banner"
                        role="alert"
                        data-testid="quality-flags-banner"
                    >
                        <AlertTriangle size={16} aria-hidden="true" />
                        <div className="quality-flags-banner-body">
                            <strong>Parse quality flags</strong>
                            <ul>
                                {qualityReasons.map((reason) => (
                                    <li key={reason}>{reason}</li>
                                ))}
                            </ul>
                        </div>
                    </div>
                )}
                <div 
                    ref={containerRef} 
                    className="html-renderer-container"
                    style={{ display: paneMode === 'rendered' ? 'block' : 'none' }}
                    onClick={(e) => e.stopPropagation()} // Stop bubble up to prevent clearing selection
                />

                {paneMode === 'plain' && (
                    <div className="html-renderer-container raw-mode">
                        <pre className="plain-text-view">
                            {section?.plain_text || ''}
                        </pre>
                    </div>
                )}

                {paneMode === 'html' && (
                    <div className="html-renderer-container raw-mode" style={{ padding: 24 }}>
                        <pre style={{ 
                            margin: 0, 
                            padding: 16, 
                            backgroundColor: 'var(--color-bg-primary)', 
                            border: '1px solid var(--color-border)', 
                            borderRadius: 'var(--radius-md)', 
                            whiteSpace: 'pre-wrap', 
                            wordBreak: 'break-all', 
                            fontFamily: 'monospace', 
                            fontSize: '0.8rem', 
                            color: 'var(--color-text-primary)',
                            overflowX: 'auto',
                            lineHeight: 1.5,
                            userSelect: 'text'
                        }}>
                            {htmlContent}
                        </pre>
                    </div>
                )}

                {paneMode === 'json' && (
                    <div className="html-renderer-container raw-mode" style={{ padding: 24 }}>
                        <pre style={{ 
                            margin: 0, 
                            padding: 16, 
                            backgroundColor: 'var(--color-bg-primary)', 
                            border: '1px solid var(--color-border)', 
                            borderRadius: 'var(--radius-md)', 
                            whiteSpace: 'pre-wrap', 
                            wordBreak: 'break-all', 
                            fontFamily: 'monospace', 
                            fontSize: '0.8rem', 
                            color: 'var(--color-text-primary)',
                            overflowX: 'auto',
                            lineHeight: 1.5,
                            userSelect: 'text'
                        }}>
                            {JSON.stringify(section || { id: sectionId, html_content: htmlContent, footnotes }, null, 2)}
                        </pre>
                    </div>
                )}

                {popoverCoords && selectionData && paneMode === 'rendered' && (
                    <AnnotationPopover 
                        selectionText={selectionData.text}
                        coords={popoverCoords}
                        onSave={handleSaveAnnotation}
                        onCancel={handleCancelAnnotation}
                    />
                )}

                {hoverFootnote && paneMode === 'rendered' && (
                    <div style={{
                        position: 'absolute',
                        top: hoverFootnote.coords.top,
                        left: hoverFootnote.coords.left,
                        transform: 'translate(-50%, -100%)',
                        zIndex: 200,
                        pointerEvents: 'none'
                    }}>
                        <div style={{
                            backgroundColor: 'var(--color-bg-secondary)',
                            border: '1px solid var(--color-border-strong)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '8px 12px',
                            boxShadow: 'var(--shadow-md)',
                            fontSize: '0.8rem',
                            color: 'var(--color-text-primary)',
                            maxWidth: 280,
                            animation: 'popFade 0.1s ease-out'
                        }}>
                            <div style={{ fontWeight: 800, color: 'var(--color-accent)', marginBottom: 2 }}>Footnote {hoverFootnote.marker}</div>
                            <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)' }}>
                                {hoverFootnote.text
                                    ? hoverFootnote.text.split('\n')[0].trim().slice(0, 200) +
                                      (hoverFootnote.text.split('\n')[0].trim().length > 200 || hoverFootnote.text.includes('\n') ? '…' : '')
                                    : ''
                                }
                            </div>
                        </div>
                    </div>
                )}

                {clickFootnote && paneMode === 'rendered' && (
                    <div 
                        id="footnote-click-popup"
                        style={{
                            position: 'absolute',
                            top: clickFootnote.coords.top,
                            left: clickFootnote.coords.left,
                            transform: 'translateX(-50%)',
                            zIndex: 210
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div style={{
                            backgroundColor: 'var(--color-bg-secondary)',
                            border: '1px solid var(--color-border-strong)',
                            borderRadius: 'var(--radius-md)',
                            padding: '16px',
                            boxShadow: 'var(--shadow-lg)',
                            fontSize: '0.85rem',
                            color: 'var(--color-text-primary)',
                            maxWidth: 320,
                            animation: 'popFade 0.15s ease-out'
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 16 }}>
                                <span style={{ fontWeight: 800, color: 'var(--color-accent)' }}>Footnote {clickFootnote.marker}</span>
                                <button 
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        color: 'var(--color-text-muted)',
                                        cursor: 'pointer',
                                        fontSize: '1.2rem',
                                        lineHeight: '1',
                                        fontWeight: 'bold',
                                        padding: '2px 6px'
                                    }}
                                    onClick={() => setClickFootnote(null)}
                                >
                                    &times;
                                </button>
                            </div>
                            <div style={{ lineHeight: 1.5, color: 'var(--color-text-secondary)', whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)' }}>{clickFootnote.text}</div>
                        </div>
                    </div>
                )}

                {paneMode === 'rendered' && (
                    <div onClick={(e) => e.stopPropagation()}>
                        <FootnotePanel 
                            footnotes={footnotes} 
                            annotations={annotations}
                            onFootnoteSelect={handleFootnoteSelect}
                        />
                    </div>
                )}
            </div>

        </div>
    );
};

// Helper: Maps plain text character offsets back to HTML DOM nodes
const createRangeFromOffsets = (container, startOffset, endOffset) => {
    const range = document.createRange();
    let currentOffset = 0;
    let startNode = null;
    let startCharOffset = 0;
    let endNode = null;
    let endCharOffset = 0;

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
    let node;
    while ((node = walker.nextNode())) {
        const length = node.textContent.length;
        
        if (!startNode && currentOffset + length >= startOffset) {
            startNode = node;
            startCharOffset = startOffset - currentOffset;
        }
        if (!endNode && currentOffset + length >= endOffset) {
            endNode = node;
            endCharOffset = endOffset - currentOffset;
            break;
        }
        currentOffset += length;
    }

    if (startNode && endNode) {
        try {
            range.setStart(startNode, startCharOffset);
            range.setEnd(endNode, endCharOffset);
            return range;
        } catch (e) {
            console.error('Error setting range offsets:', e);
        }
    }
    return null;
};

export default HtmlPanel;
