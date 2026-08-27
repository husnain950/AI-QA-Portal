import React, { useRef, useEffect, useState } from 'react';
import { useTextSelection } from '../../hooks/useTextSelection';
import { useReviewStore } from '../../stores/reviewStore';
import AnnotationPopover from '../annotations/AnnotationPopover';
import FootnotePanel from '../footnotes/FootnotePanel';
import { formatQualityFlagList } from '../../utils/qualityFlags';
import { useUiStore } from '../../stores/uiStore';
import SegmentedControl from '../ui/SegmentedControl';
import CopyButton from '../ui/CopyButton';
import EmptyState from '../ui/EmptyState';
import { Code, Eye, AlignLeft, AlertTriangle, Braces, FileQuestion } from 'lucide-react';
import { findFootnoteForCite } from '../../utils/footnoteCite';

const MODE_TITLES = {
    rendered: 'Parsed HTML Content',
    plain: 'Extracted Plain Text',
    html: 'Raw HTML Markup',
    json: 'Raw Section JSON',
};

const MODE_HINTS = {
    rendered: 'Highlight text in this pane to report discrepancies',
    plain: 'Punctuation-faithful extracted text',
    html: 'Raw HTML markup code',
    json: 'Raw JSON data for this section',
};

const JUMP_HIGHLIGHT_MS = 1600;

const HtmlPanel = ({ section, sectionId, htmlContent, footnotes, qualityFlags }) => {
    const qualityReasons = formatQualityFlagList(
        qualityFlags ?? section?.quality_flags,
    );
    const containerRef = useRef(null);
    const pushToast = useUiStore((s) => s.pushToast);
    const {
        annotations,
        createAnnotation,
        fetchAnnotations,
        setActiveFootnoteId,
        activeFootnoteId,
        citeJumpNonce,
    } = useReviewStore();
    const [popoverCoords, setPopoverCoords] = useState(null);
    const [selectionData, setSelectionData] = useState(null);
    const [paneMode, setPaneMode] = useState('rendered');
    const lastCiteJumpNonce = useRef(0);

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

    // Inject highlighting marks into rendered DOM & bind cite → footnote jumps
    useEffect(() => {
        const container = containerRef.current;
        if (!container || !htmlContent) return;

        // Reset DOM to clean state
        container.innerHTML = htmlContent;

        const cites = container.querySelectorAll('.cite');
        cites.forEach((cite) => {
            const titleText = cite.getAttribute('title');
            if (titleText) {
                cite.setAttribute('data-footnote-text', titleText);
                cite.removeAttribute('title'); // Disable default slow native browser tooltip
            }

            const marker = (cite.textContent || '').trim();
            if (marker) {
                cite.setAttribute('data-fn-marker', marker);
            }
            const matched = findFootnoteForCite(cite, footnotes);
            if (matched?.id != null) {
                cite.setAttribute('data-fn-id', String(matched.id));
            }

            const handleClick = (e) => {
                e.stopPropagation();
                e.preventDefault();
                const hit = findFootnoteForCite(cite, footnotes);
                if (hit?.id != null) {
                    setActiveFootnoteId(hit.id);
                }
            };

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
    }, [htmlContent, annotations, footnotes, setActiveFootnoteId]);

    // Footnote card → cite: scroll and flash the matching marker
    useEffect(() => {
        if (!citeJumpNonce || citeJumpNonce === lastCiteJumpNonce.current) return;
        lastCiteJumpNonce.current = citeJumpNonce;
        if (!activeFootnoteId) return;

        const container = containerRef.current;
        if (!container) return;

        const cite = Array.from(container.querySelectorAll('.cite')).find(
            (el) => el.getAttribute('data-fn-id') === String(activeFootnoteId),
        );
        if (!cite) return;

        cite.scrollIntoView({ behavior: 'smooth', block: 'center' });
        cite.classList.add('cite-jump-target');
        const timer = setTimeout(() => {
            cite.classList.remove('cite-jump-target');
        }, JUMP_HIGHLIGHT_MS);
        return () => {
            clearTimeout(timer);
            cite.classList.remove('cite-jump-target');
        };
    }, [citeJumpNonce, activeFootnoteId]);

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

    const copyText = () => {
        if (paneMode === 'json') {
            return JSON.stringify(
                section || { id: sectionId, html_content: htmlContent, footnotes },
                null,
                2,
            );
        }
        if (paneMode === 'plain') return section?.plain_text || '';
        return htmlContent;
    };

    return (
        <div className="flex flex-col" style={{ height: '100%' }} onClick={handleCancelAnnotation}>
            <div className="panel-header html-panel-header">
                <div className="html-panel-title" title={MODE_HINTS[paneMode]}>
                    <span className="panel-title">{MODE_TITLES[paneMode]}</span>
                </div>
                <div className="html-panel-controls" onClick={(e) => e.stopPropagation()}>
                    <SegmentedControl
                        ariaLabel="Content view mode"
                        value={paneMode}
                        onChange={setPaneMode}
                        options={[
                            { value: 'rendered', label: 'Rendered', icon: <Eye size={13} />, title: 'Rendered HTML — highlight text to report issues' },
                            { value: 'plain', label: 'Plain Text', icon: <AlignLeft size={13} />, title: 'Punctuation-faithful extracted text' },
                            { value: 'html', label: 'Raw HTML', icon: <Code size={13} />, title: 'Raw HTML markup' },
                            { value: 'json', label: 'Raw JSON', icon: <Braces size={13} />, title: 'Raw section JSON' },
                        ]}
                    />
                    <CopyButton
                        className="btn btn-sm btn-secondary"
                        getText={copyText}
                        label="Copy"
                        copiedLabel="Copied!"
                        title={`Copy ${paneMode === 'json' ? 'JSON' : paneMode === 'plain' ? 'plain text' : 'HTML'} to clipboard`}
                        onError={() => pushToast({ type: 'error', message: 'Copy to clipboard failed' })}
                    />
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

                {paneMode === 'rendered' && !htmlContent && (
                    <EmptyState
                        compact
                        icon={<FileQuestion size={32} />}
                        title="No parsed HTML"
                        message="This leaf has no HTML content in the active JSON version. Check the plain-text view or the raw JSON."
                    />
                )}

                <div
                    ref={containerRef}
                    className="html-renderer-container"
                    style={{ display: paneMode === 'rendered' && htmlContent ? 'block' : 'none' }}
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
                    <div className="html-renderer-container raw-mode raw-mode-pad">
                        <pre className="raw-pre">
                            {htmlContent}
                        </pre>
                    </div>
                )}

                {paneMode === 'json' && (
                    <div className="html-renderer-container raw-mode raw-mode-pad">
                        <pre className="raw-pre">
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
