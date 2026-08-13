import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
    AlertTriangle,
    Check,
    Loader2,
    Sparkles,
    X,
} from 'lucide-react';

import { usePdfDocument, usePdfPageRenderer } from '../../hooks/usePdfRenderer';
import { useAiFixStore } from '../../stores/aiFixStore';
import { useDocumentStore } from '../../stores/documentStore';
import { useReviewStore } from '../../stores/reviewStore';
import { useUiStore } from '../../stores/uiStore';
import { api } from '../../utils/api';
import {
    changeSummary,
    classifyDiffLine,
    htmlChangeHints,
    pagesSentToModel,
    seedInstructions,
    validationSummary,
} from '../../utils/aiFix';

const PREVIEW_ZOOM = 0.62;

/** Compact canvas for one PDF page the model was shown. Always renders (no lazy skip). */
const AiFixPdfPage = ({ pdfDoc, pageNumber }) => {
    const canvasRef = useRef(null);
    const { loading, error, blank } = usePdfPageRenderer(
        pdfDoc,
        pageNumber,
        PREVIEW_ZOOM,
        canvasRef,
    );

    return (
        <div className="pdf-canvas-wrapper ai-fix-pdf-page" data-pdf-page={pageNumber}>
            {loading && (
                <div className="ai-fix-pdf-status">
                    <Loader2 className="animate-spin" size={18} />
                </div>
            )}
            {error && (
                <p className="ai-fix-pdf-status is-error">Could not render page {pageNumber}</p>
            )}
            {blank && !error && (
                <p className="ai-fix-pdf-status is-error">Page {pageNumber} did not render</p>
            )}
            <canvas ref={canvasRef} className="pdf-canvas" />
            <span className="ai-fix-pdf-folio">Page {pageNumber}</span>
        </div>
    );
};

/** The same PDF pages attached to the model request (start–end, capped at 4). */
const AiFixPdfPreview = ({ pdfUrl, pages }) => {
    const { pdfDoc, loading, error, numPages } = usePdfDocument(pdfUrl);
    const visible = useMemo(
        () => pages.filter((page) => !numPages || page <= numPages),
        [pages, numPages],
    );

    if (!pdfUrl) {
        return <p className="ai-fix-hint">No PDF is attached to this document.</p>;
    }

    return (
        <div className="ai-fix-pdf-preview pdf-scroll-container">
            {loading && (
                <div className="ai-fix-pdf-status">
                    <Loader2 className="animate-spin" size={20} />
                    <span>Loading PDF pages…</span>
                </div>
            )}
            {error && !loading && (
                <p className="ai-fix-pdf-status is-error">{error.message || 'Failed to load PDF'}</p>
            )}
            {!error && pdfDoc && visible.map((pageNumber) => (
                <AiFixPdfPage key={pageNumber} pdfDoc={pdfDoc} pageNumber={pageNumber} />
            ))}
        </div>
    );
};

const RenderedLeaf = ({ html, label, proposed = false }) => {
    const bodyRef = useRef(null);

    useEffect(() => {
        const root = bodyRef.current;
        if (!root) return;
        root.querySelectorAll('.proviso').forEach((node) => {
            node.setAttribute('data-ai-fix-tag', node.tagName.toLowerCase());
        });
        root.querySelector('p.proviso, span.proviso, .proviso')
            ?.scrollIntoView?.({ block: 'center', behavior: 'instant' });
    }, [html]);

    return (
        <section className="ai-fix-html-pane">
            <h4>{label}</h4>
            <div
                ref={bodyRef}
                className={`html-renderer-container ai-fix-rendered${proposed ? ' is-proposed' : ''}`}
                dangerouslySetInnerHTML={{ __html: html || '' }}
            />
        </section>
    );
};

const AiFixWorkspace = ({ pdfUrl, pdfPages, currentHtml, proposedHtml = null }) => (
    <div className="ai-fix-workspace" data-has-proposed={proposedHtml != null ? '1' : '0'}>
        <section className="ai-fix-pdf-pane">
            <h4>
                PDF page{pdfPages.length === 1 ? '' : 's'} sent
                {pdfPages.length
                    ? ` (${pdfPages[0]}${pdfPages.length > 1 ? `–${pdfPages[pdfPages.length - 1]}` : ''})`
                    : ''}
            </h4>
            <AiFixPdfPreview pdfUrl={pdfUrl} pages={pdfPages} />
        </section>
        <RenderedLeaf label="Current parse" html={currentHtml} />
        {proposedHtml != null && (
            <RenderedLeaf label="Proposed fix" html={proposedHtml} proposed />
        )}
    </div>
);

/**
 * The AI fix loop, as a modal over the review workspace:
 * 1. compose — reviewer writes instructions (pre-seeded from open annotations)
 * 2. loading — the model reads the leaf JSON + PDF page images
 * 3. compare — current vs proposed side-by-side + plain-text diff + validation
 * Approve records a persistent overlay and creates the next JSON version.
 */
const AiFixPanel = ({ open, onClose, documentId, section, onApplied }) => {
    const pushToast = useUiStore((s) => s.pushToast);
    const annotations = useReviewStore((s) => s.annotations);
    const activeDocument = useDocumentStore((s) => s.activeDocument);
    const { requestFix, approve, reject, fetchModels, fetchProposals } = useAiFixStore();
    const models = useAiFixStore((s) => s.models);
    const defaultModel = useAiFixStore((s) => s.defaultModel);
    const storedProposals = useAiFixStore((s) => s.proposals);
    const pdfUrl = activeDocument?.pdf_filename
        ? api.getFileUrl(activeDocument.pdf_filename)
        : '';
    const pdfPages = useMemo(
        () => pagesSentToModel(section?.start_page, section?.end_page),
        [section?.start_page, section?.end_page],
    );

    const [instructions, setInstructions] = useState('');
    const [model, setModel] = useState('');
    const [proposal, setProposal] = useState(null);
    const [phase, setPhase] = useState('compose'); // compose | loading | compare
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open || !section?.id) return;
        let cancelled = false;
        const applyPending = (list) => {
            const pending = (list || []).find(
                (item) => item.section_id === section.id && item.status === 'proposed' && item.proposed,
            );
            if (cancelled) return pending;
            setError('');
            setInstructions(pending?.instructions || seedInstructions(annotations));
            setProposal(pending || null);
            setPhase(pending ? 'compare' : 'compose');
            return pending;
        };
        applyPending(storedProposals);
        fetchModels();
        if (documentId) {
            fetchProposals(documentId).then((list) => applyPending(list));
        }
        return () => { cancelled = true; };
        // Seed once per opening; later annotation edits shouldn't clobber typing.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, section?.id]);

    useEffect(() => {
        if (!model && defaultModel) setModel(defaultModel);
    }, [defaultModel, model]);

    // Escape closes the panel (the request keeps running server-side while
    // loading; the proposal is picked up again the next time it opens).
    useEffect(() => {
        if (!open) return undefined;
        const onKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onClose();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    const validation = useMemo(
        () => validationSummary(proposal?.validation),
        [proposal],
    );
    const summaryLines = useMemo(() => changeSummary(proposal?.diff), [proposal]);
    const markupHints = useMemo(
        () => htmlChangeHints(section?.html_content, proposal?.proposed?.html),
        [section?.html_content, proposal?.proposed?.html],
    );

    if (!open || !section) return null;

    const handleRequest = async () => {
        if (!instructions.trim()) {
            setError('Describe what the pipeline got wrong first.');
            return;
        }
        setPhase('loading');
        setError('');
        try {
            const result = await requestFix(documentId, section.id, instructions, model);
            setProposal(result);
            setPhase('compare');
            if (result.status === 'failed') {
                setError(result.error || 'The model reply failed validation.');
            }
        } catch (e) {
            setError(e.message || 'The fix request failed.');
            setPhase('compose');
        }
    };

    const handleApprove = async () => {
        setBusy(true);
        setError('');
        try {
            const result = await approve(proposal.id);
            pushToast({
                type: 'success',
                message: `AI fix applied as version ${result.version_no}. The overlay will persist across re-syncs.`,
            });
            onApplied?.();
            onClose();
        } catch (e) {
            setError(e.message || 'Approval failed.');
        } finally {
            setBusy(false);
        }
    };

    const handleReject = async () => {
        setBusy(true);
        setError('');
        try {
            await reject(proposal.id);
            pushToast({ type: 'info', message: 'Proposal rejected. Nothing was changed.' });
            setProposal(null);
            setPhase('compose');
        } catch (e) {
            setError(e.message || 'Rejection failed.');
        } finally {
            setBusy(false);
        }
    };

    const diffLines = proposal?.diff?.plain_text_diff || [];

    // Portal to body: the toolbar is a glass-panel with backdrop-filter + overflow
    // hidden, which would otherwise clip this fixed overlay to 64px.
    return createPortal(
        <div className="ai-fix-overlay" role="dialog" aria-modal="true" aria-label="AI fix">
            <div className="ai-fix-panel glass-panel">
                <header className="ai-fix-header">
                    <h3>
                        <Sparkles size={16} />
                        AI fix — Section {section.section_code}
                        {section.section_heading ? `: ${section.section_heading}` : ''}
                    </h3>
                    <button type="button" onClick={onClose} aria-label="Close AI fix panel">
                        <X size={16} />
                    </button>
                </header>

                {error && (
                    <p className="ai-fix-error">
                        <AlertTriangle size={14} /> {error}
                    </p>
                )}

                {phase === 'compose' && (
                    <div className="ai-fix-compose">
                        <p className="ai-fix-hint">
                            The model receives this section's JSON, images of PDF page
                            {section.end_page !== section.start_page
                                ? `s ${section.start_page}–${section.end_page}`
                                : ` ${section.start_page}`}
                            , and your instructions. It proposes a corrected section —
                            nothing is applied until you approve it.
                        </p>
                        <AiFixWorkspace
                            pdfUrl={pdfUrl}
                            pdfPages={pdfPages}
                            currentHtml={section.html_content}
                        />
                        <textarea
                            value={instructions}
                            onChange={(event) => setInstructions(event.target.value)}
                            placeholder="Describe what the transformation got wrong, e.g. 'The proviso after subsection (2) is missing' or 'Footnote 3 text was merged into the body.'"
                            rows={4}
                        />
                        <div className="ai-fix-actions">
                            {models.length > 0 && (
                                <label className="ai-fix-model-picker">
                                    <span>Model</span>
                                    <select
                                        value={model}
                                        onChange={(event) => setModel(event.target.value)}
                                        title="Which gateway model to ask for the fix"
                                    >
                                        {models.map((name) => (
                                            <option key={name} value={name}>
                                                {name}
                                                {name === defaultModel ? ' (default)' : ''}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                            )}
                            <button type="button" className="btn btn-secondary" onClick={onClose}>
                                Cancel
                            </button>
                            <button type="button" className="btn btn-primary" onClick={handleRequest}>
                                <Sparkles size={14} />
                                Request fix
                            </button>
                        </div>
                    </div>
                )}

                {phase === 'loading' && (
                    <div className="ai-fix-loading">
                        <Loader2 className="animate-spin" size={28} />
                        <p>Sending the section JSON and PDF pages to the model…</p>
                        <p className="ai-fix-hint">This usually takes under a minute.</p>
                        <button type="button" className="btn btn-sm btn-secondary" onClick={onClose}>
                            Close and keep working — the proposal will be here when you reopen
                        </button>
                    </div>
                )}

                {phase === 'compare' && proposal && (
                    <div className="ai-fix-compare">
                        <div className="ai-fix-meta">
                            <span className={`badge badge-${proposal.status === 'proposed' ? 'pending' : 'flagged'}`}>
                                {proposal.status}
                            </span>
                            {proposal.model_name && <span>model: {proposal.model_name}</span>}
                            {summaryLines.map((line) => (
                                <span key={line}>{line}</span>
                            ))}
                            {markupHints.map((line) => (
                                <span key={line} className="ai-fix-markup-hint">{line}</span>
                            ))}
                        </div>

                        {(validation.errors.length > 0 || validation.warnings.length > 0) && (
                            <ul className="ai-fix-validation">
                                {validation.errors.map((message) => (
                                    <li key={message} className="is-error">
                                        <AlertTriangle size={13} /> {message}
                                    </li>
                                ))}
                                {validation.warnings.map((message) => (
                                    <li key={message} className="is-warning">
                                        <AlertTriangle size={13} /> {message}
                                    </li>
                                ))}
                            </ul>
                        )}

                        <AiFixWorkspace
                            pdfUrl={pdfUrl}
                            pdfPages={pdfPages}
                            currentHtml={section.html_content}
                            proposedHtml={proposal.proposed?.html || ''}
                        />

                        {diffLines.length > 0 && (
                            <div className="ai-fix-diff">
                                <h4>Plain-text changes</h4>
                                <pre>
                                    {diffLines.map((line, index) => (
                                        <div key={index} className={`diff-${classifyDiffLine(line)}`}>
                                            {line}
                                        </div>
                                    ))}
                                </pre>
                            </div>
                        )}
                        {diffLines.length === 0 && proposal.status === 'proposed' && (
                            <p className="ai-fix-hint">
                                {markupHints.length
                                    ? `Wording is unchanged; HTML structure moved (${markupHints.join(', ')}). Scroll the rendered panes to compare.`
                                    : 'No plain-text or HTML-structure differences — check footnotes before approving.'}
                            </p>
                        )}

                        <div className="ai-fix-actions">
                            <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={() => {
                                    setProposal(null);
                                    setPhase('compose');
                                    setError('');
                                }}
                                disabled={busy}
                            >
                                Edit instructions & retry
                            </button>
                            <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={handleReject}
                                disabled={busy || proposal.status === 'failed'}
                            >
                                <X size={14} />
                                Reject
                            </button>
                            <button
                                type="button"
                                className="btn btn-primary"
                                onClick={handleApprove}
                                disabled={busy || proposal.status !== 'proposed' || validation.blocked}
                                title={
                                    validation.blocked
                                        ? 'Validation errors block approval'
                                        : 'Apply as a new version + persistent overlay'
                                }
                            >
                                {busy ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                                Approve & apply
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>,
        document.body,
    );
};

export default AiFixPanel;
