import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
    AlertCircle, ArrowLeft, ArrowRight, GitBranch, History, Loader2, X,
} from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import Sidebar from '../components/layout/Sidebar';
import SplitPane from '../components/review/SplitPane';
import PdfPanel from '../components/review/PdfPanel';
import HtmlPanel from '../components/review/HtmlPanel';
import ReviewToolbar from '../components/review/ReviewToolbar';
import NewVersionButton from '../components/review/NewVersionButton';
import Breadcrumbs from '../components/review/Breadcrumbs';
import DocumentTags from '../components/dashboard/DocumentTags';
import DocumentHealth from '../components/dashboard/DocumentHealth';
import SegmentedControl from '../components/ui/SegmentedControl';
import ProgressBar from '../components/ui/ProgressBar';

import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useAiFixStore } from '../stores/aiFixStore';
import { useUiStore } from '../stores/uiStore';
import { useKeyboardNav } from '../hooks/useKeyboardNav';
import { api, versionsApi } from '../utils/api';
import VersionPanel from '../components/review/VersionPanel';
import { formatLeafIdentity, formatLeafJsonPath } from '../utils/tocLabels';
import CopyButton from '../components/ui/CopyButton';
import { TAG_NEEDS_REVIEW, TAG_PROVISIONAL } from '../utils/documentTags';
import { recordDocumentView } from '../utils/recents';
import { documentLane, laneLabel } from '../utils/corpusLanes';
import { editionOf } from '../utils/editions';
import { fullDateTime } from '../utils/time';
import { timelinePath } from '../utils/timeline';

const ReviewPage = () => {
    const { documentId, sectionId } = useParams();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const reviewSessionId = searchParams.get('session');
    const queryFindingId = searchParams.get('finding');

    const [versionsOpen, setVersionsOpen] = useState(false);
    const [editions, setEditions] = useState(null);
    const [queueFinding, setQueueFinding] = useState(
        queryFindingId ? { id: Number(queryFindingId), triage: 'new' } : null,
    );
    const [queueBusy, setQueueBusy] = useState(false);
    const pushToast = useUiStore((s) => s.pushToast);

    const {
        activeDocument,
        sections,
        activeSection,
        activeSectionError,
        pageSections,
        fetchDocument,
        fetchSections,
        fetchSection,
        fetchSectionsByPage,
        refreshReviewData,
    } = useDocumentStore();

    const { currentPage, viewMode, setViewMode, setCurrentPage } = useReviewStore();
    const fetchAiProposals = useAiFixStore((s) => s.fetchProposals);
    const [initialLoad, setInitialLoad] = useState(true);
    const [error, setError] = useState('');
    const currentSectionIndex = sections.findIndex(
        (section) => section.id === activeSection?.id,
    );

    const navigateQueueResult = useCallback((result) => {
        const next = result?.current;
        setQueueFinding(next || null);
        if (!next) {
            pushToast({ type: 'success', message: 'This review-session snapshot is complete' });
            navigate('/', { replace: true });
            return;
        }
        const query = new URLSearchParams({
            session: reviewSessionId,
            finding: String(next.id),
        });
        navigate(`/review/${next.document_id}/${next.section_id}?${query}`);
    }, [navigate, pushToast, reviewSessionId]);

    const runQueueAction = useCallback(async (action, triage = null) => {
        if (!reviewSessionId || queueBusy) return;
        setQueueBusy(true);
        try {
            const body = triage && queueFinding ? {
                finding_id: queueFinding.id,
                triage,
                expected_prior: queueFinding.triage || 'new',
                note: '',
            } : {};
            const result = await api.post(
                `/v2/review-sessions/${reviewSessionId}/${action}`,
                body,
            );
            navigateQueueResult(result);
        } catch (err) {
            pushToast({ type: 'error', message: err.message || 'Review-session action failed' });
        } finally {
            setQueueBusy(false);
        }
    }, [navigateQueueResult, pushToast, queueBusy, queueFinding, reviewSessionId]);

    useEffect(() => {
        if (!reviewSessionId) return undefined;
        const controller = new AbortController();
        api.get(`/v2/review-sessions/${reviewSessionId}`, { signal: controller.signal })
            .then((session) => setQueueFinding(session.current || null))
            .catch((err) => {
                if (err.code !== 'cancelled') {
                    pushToast({ type: 'error', message: err.message || 'Could not resume review session' });
                }
            });
        return () => controller.abort();
    }, [pushToast, reviewSessionId]);

    useEffect(() => {
        if (!reviewSessionId || !queueFinding?.id) return undefined;
        const clientSessionId = sessionStorage.getItem('crx-review-client-session');
        if (!clientSessionId) return undefined;
        const renew = () => api.post(`/v2/review-assignments/${queueFinding.id}`, {
            client_session_id: clientSessionId,
        }).catch(() => {});
        renew();
        const timer = window.setInterval(renew, 10 * 60_000);
        return () => window.clearInterval(timer);
    }, [queueFinding?.id, reviewSessionId]);

    const loadEditions = useCallback(async (docId) => {
        try {
            const data = await versionsApi.editions(docId);
            setEditions(data);
        } catch {
            setEditions(null);
        }
    }, []);

    const navigateBySection = (offset) => {
        if (viewMode !== 'section' || currentSectionIndex < 0) return;
        const target = sections[currentSectionIndex + offset];
        if (target) {
            navigate(`/review/${documentId}/${target.id}`);
        }
    };

    const switchEdition = async (siblingId) => {
        if (!siblingId || siblingId === documentId) return;
        const sectionCode = activeSection?.section_code;
        if (sectionCode) {
            try {
                const siblingSections = await api.get(`/documents/${siblingId}/sections`);
                const match = (siblingSections || []).find(
                    (sec) => sec.section_code === sectionCode,
                );
                if (match) {
                    navigate(`/review/${siblingId}/${match.id}`);
                    return;
                }
            } catch {
                // fall through to document root
            }
        }
        navigate(`/review/${siblingId}`);
    };

    useKeyboardNav({
        onArrowLeft: () => {
            if (viewMode === 'page' && currentPage > 1) {
                setCurrentPage(currentPage - 1);
            }
        },
        onArrowRight: () => {
            if (
                viewMode === 'page'
                && activeDocument
                && currentPage < activeDocument.total_pages
            ) {
                setCurrentPage(currentPage + 1);
            }
        },
        onPreviousSection: () => navigateBySection(-1),
        onNextSection: () => navigateBySection(1),
    });

    useEffect(() => {
        const loadDocAndSections = async () => {
            setInitialLoad(true);
            try {
                // Fetch document metadata
                const doc = await fetchDocument(documentId);
                if (!doc) {
                    setError('Document not found');
                    return;
                }

                await fetchSections(documentId);
                await loadEditions(documentId);
                fetchAiProposals(documentId); // fire-and-forget: only feeds badges
            } catch (err) {
                setError('Failed to load review data');
                console.error(err);
            } finally {
                setInitialLoad(false);
            }
        };

        if (documentId) {
            recordDocumentView(documentId);
            loadDocAndSections();
        }
    }, [documentId, fetchDocument, fetchSections, loadEditions, fetchAiProposals]);

    // Fetch page sections when in Page View
    useEffect(() => {
        if (viewMode === 'page' && currentPage) {
            fetchSectionsByPage(documentId, currentPage);
        }
    }, [viewMode, currentPage, documentId, fetchSectionsByPage]);

    // Synchronize active section with URL sectionId; force PDF to leaf start_page on change.
    useEffect(() => {
        if (initialLoad || sections.length === 0 || viewMode !== 'section') return;

        if (sectionId) {
            if (!activeSection || activeSection.id !== sectionId) {
                // Prefer immediate start_page from TOC so PdfPanel never clamps a stale
                // page into the new range (e.g. landing on the end of 241–254).
                const tocSection = sections.find((s) => s.id === sectionId);
                if (tocSection?.start_page) {
                    setCurrentPage(tocSection.start_page);
                }

                const loadSection = async () => {
                    const sec = await fetchSection(documentId, sectionId);
                    if (sec) {
                        setCurrentPage(sec.start_page || 1);
                    }
                };
                loadSection();
            }
        } else {
            // No sectionId in URL, redirect to the first pending section (or first section)
            const firstPending = sections.find(s => s.review_status === 'pending') || sections[0];
            if (firstPending) {
                navigate(`/review/${documentId}/${firstPending.id}`, { replace: true });
            }
        }
    }, [sectionId, initialLoad, sections, viewMode, activeSection, documentId, fetchSection, setCurrentPage, navigate]);

    if (initialLoad) {
        return (
            <div className="review-fullscreen-state">
                <Loader2 className="animate-spin" size={32} style={{ color: 'var(--color-accent)' }} />
                <span>Loading workspace…</span>
            </div>
        );
    }

    if (error || !activeDocument) {
        return (
            <div className="review-fullscreen-state">
                <AlertCircle size={44} style={{ color: 'var(--color-error)' }} />
                <h3>Workspace error</h3>
                <p>{error || 'Document metadata could not be fetched'}</p>
                <button className="btn btn-primary" onClick={() => navigate('/library')}>
                    <ArrowLeft size={15} />
                    <span>Back to Library</span>
                </button>
            </div>
        );
    }

    const pdfUrl = api.getFileUrl(activeDocument.pdf_filename);

    const leftPanel = (
        <PdfPanel pdfUrl={pdfUrl} />
    );

    const rightPanel = (
        <div className="flex flex-col" style={{ height: '100%' }}>
            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                {viewMode === 'section' ? (
                    activeSection ? (
                        <HtmlPanel
                            section={activeSection}
                            sectionId={activeSection.id}
                            htmlContent={activeSection.html_content}
                            footnotes={activeSection.footnotes}
                        />
                    ) : activeSectionError === 'removed' ? (
                        // Sections are hard-deleted, so a URL naming a retired id
                        // 404s. This used to leave the PREVIOUS leaf mounted -- its
                        // HTML, its footnotes, its toolbar -- while the URL and
                        // "Leaf N of M" referred to the dead one, so a reviewer could
                        // approve or annotate the wrong provision after a resync.
                        // The backend already models this for annotations
                        // (`anchor_status='orphaned'` with a snapshot); this is the
                        // section-level equivalent, which was never wired up.
                        <div className="review-panel-empty" data-testid="section-removed">
                            <strong>This leaf is no longer in the document.</strong>
                            <p>
                                A newer parse removed it, so the id in this link no
                                longer resolves. Pick a section from the Table of
                                Contents to carry on.
                            </p>
                            {sections.length > 0 ? (
                                <button
                                    type="button"
                                    className="btn btn-sm btn-secondary"
                                    onClick={() => navigate(`/review/${documentId}/${sections[0].id}`)}
                                >
                                    Go to the first section
                                </button>
                            ) : null}
                        </div>
                    ) : activeSectionError === 'failed' ? (
                        <div className="review-panel-empty" data-testid="section-failed">
                            <strong>This section could not be loaded.</strong>
                            <p>That is a request failure, not an empty section.</p>
                            <button
                                type="button"
                                className="btn btn-sm btn-secondary"
                                onClick={() => fetchSection(documentId, sectionId)}
                            >
                                Retry
                            </button>
                        </div>
                    ) : (
                        <div className="review-panel-empty">
                            Select a section from the Table of Contents to begin review
                        </div>
                    )
                ) : (
                    /* Page View: list of sections covering current page */
                    pageSections.length > 0 ? (
                        <div style={{ flex: 1, overflowY: 'auto' }}>
                            {pageSections.map(sec => (
                                <div key={sec.id} className="page-view-section">
                                    <div className="page-view-section-head">
                                        <span className="page-view-section-title">
                                            Section {sec.section_code}: {sec.section_heading}
                                        </span>
                                        <span className={`badge badge-${sec.review_status}`}>
                                            {sec.review_status === 'has_issues' ? 'flagged' : sec.review_status}
                                        </span>
                                    </div>
                                    <HtmlPanel
                                        section={sec}
                                        sectionId={sec.id}
                                        htmlContent={sec.html_content}
                                        footnotes={sec.footnotes}
                                    />
                                    <ReviewToolbar section={sec} />
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="review-panel-empty">
                            No parsed sections map to page {currentPage}
                        </div>
                    )
                )}
            </div>
            {viewMode === 'section' && <ReviewToolbar />}
        </div>
    );

    const stats = activeDocument.stats || null;
    const flaggedCount = stats
        ? (stats.flagged_sections ?? stats.has_issues ?? 0)
        : 0;
    const openNotes = stats ? (stats.open_annotations ?? 0) : 0;
    const approvedCount = stats ? stats.approved : 0;
    const progressPct = activeDocument.total_sections
        ? Math.round(((approvedCount || 0) / activeDocument.total_sections) * 100)
        : 0;

    const provenanceTags = activeDocument.provenance?.tags || [];
    const showOcrLink = provenanceTags.includes(TAG_PROVISIONAL)
        || provenanceTags.includes(TAG_NEEDS_REVIEW);
    const edition = editionOf(activeDocument);
    const lane = documentLane(activeDocument);
    return (
        <AppShell
            title={activeDocument.name}
            showBackButton={true}
            sidebarContent={<Sidebar documentId={documentId} />}
        >
            <VersionPanel
                documentId={documentId}
                open={versionsOpen}
                onClose={() => setVersionsOpen(false)}
                onChanged={() => refreshReviewData()}
            />

            {activeDocument.withdrawn_at ? (
                <div className="withdrawn-banner" role="status" data-testid="withdrawn-banner">
                    <AlertCircle size={16} />
                    <div className="withdrawn-banner-body">
                        <strong>This document is no longer in the corpus.</strong>
                        The pipeline stopped producing it on{' '}
                        {fullDateTime(activeDocument.withdrawn_at)}. What you see below
                        is the last parse it made. Review here is recorded but will not
                        describe anything the pipeline currently outputs.
                    </div>
                </div>
            ) : null}

            {reviewSessionId && queueFinding ? (
                <div className="review-session-strip" aria-label="Finding review session">
                    <span>
                        Finding <strong>#{queueFinding.id}</strong>
                        <small>stable snapshot session</small>
                    </span>
                    <button
                        type="button"
                        className="btn btn-xs btn-secondary"
                        disabled={queueBusy}
                        onClick={() => runQueueAction('back')}
                    >
                        <ArrowLeft size={13} /> Back
                    </button>
                    <button
                        type="button"
                        className="btn btn-xs btn-secondary"
                        disabled={queueBusy || queueFinding.triage !== 'new'}
                        onClick={() => runQueueAction('advance', 'parse_bug')}
                    >
                        Parse bug
                    </button>
                    <button
                        type="button"
                        className="btn btn-xs btn-secondary"
                        disabled={queueBusy || queueFinding.triage !== 'new'}
                        onClick={() => runQueueAction('advance', 'source_defect')}
                    >
                        Source defect
                    </button>
                    <button
                        type="button"
                        className="btn btn-xs btn-secondary"
                        disabled={queueBusy || queueFinding.triage !== 'new'}
                        onClick={() => runQueueAction('advance', 'not_a_defect')}
                    >
                        Not a defect
                    </button>
                    <button
                        type="button"
                        className="btn btn-xs btn-primary"
                        disabled={queueBusy}
                        onClick={() => runQueueAction('next')}
                    >
                        Next highest-risk <ArrowRight size={13} />
                    </button>
                    <button
                        type="button"
                        className="btn btn-xs btn-ghost"
                        disabled={queueBusy}
                        aria-label="End review session"
                        onClick={async () => {
                            await api.delete(`/v2/review-sessions/${reviewSessionId}`);
                            navigate('/');
                        }}
                    >
                        <X size={13} /> End
                    </button>
                </div>
            ) : null}

            <div className="review-context-strip">
                <div className="review-header-tags">
                    <span className={`source-badge lane-${lane}`}>{laneLabel(lane)}</span>
                    {!edition.unknown && (
                        <span className="edition-year-badge">{edition.label}</span>
                    )}
                    <DocumentTags provenance={activeDocument.provenance} />
                    <DocumentHealth health={activeDocument.health} />
                    {stats && (
                        <span
                            className="review-doc-progress"
                            title={`${approvedCount} of ${activeDocument.total_sections} sections approved`}
                        >
                            <ProgressBar pct={progressPct} ariaHidden />
                            <span className="review-doc-progress-text">
                                {approvedCount}/{activeDocument.total_sections} approved · {flaggedCount} flagged · {openNotes} open notes
                            </span>
                        </span>
                    )}
                </div>
                <div className="review-context-actions">
                    {editions?.editions?.length > 1 && (
                        <label className="edition-switcher">
                            <span className="sr-only">Switch edition</span>
                            <select
                                value={documentId}
                                onChange={(event) => switchEdition(event.target.value)}
                                title={editions.family_title || 'Editions'}
                            >
                                {editions.editions.map((item) => (
                                    <option key={item.id} value={item.id}>
                                        {item.year_label}
                                        {item.is_current ? ' (current)' : ''}
                                        {' — '}
                                        {item.name}
                                    </option>
                                ))}
                            </select>
                        </label>
                    )}
                    {activeSection?.id && (
                        <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            title="Open family timeline for this section"
                            onClick={() => navigate(timelinePath({ sectionId: activeSection.id }))}
                        >
                            <GitBranch size={13} />
                            <span>Timeline</span>
                        </button>
                    )}
                    {showOcrLink && (
                        <button
                            type="button"
                            className="btn btn-sm btn-secondary review-ocr-link"
                            onClick={() => navigate('/?detector=ocr_disagree')}
                            title="OCR engine disagreements for this corpus"
                        >
                            OCR disagreements
                        </button>
                    )}
                    <NewVersionButton
                        documentId={documentId}
                        documentName={activeDocument?.name}
                        className="replace-json-action btn btn-sm btn-secondary"
                        onSuccess={async () => {
                            navigate(`/review/${documentId}`, { replace: true });
                            await fetchDocument(documentId);
                            await fetchSections(documentId);
                            pushToast({
                                type: 'success',
                                message: 'New JSON version is active. Open Versions to see what changed.',
                            });
                            setVersionsOpen(true);
                        }}
                    />
                    <button
                        className="versions-action btn btn-sm btn-secondary"
                        onClick={() => setVersionsOpen((open) => !open)}
                        title="Version history, diffs and rollback"
                    >
                        <History size={13} />
                        <span>Versions</span>
                    </button>
                    <SegmentedControl
                        ariaLabel="Review view mode"
                        value={viewMode}
                        onChange={(mode) => {
                            if (mode === 'section') {
                                setViewMode('section');
                                const targetId = activeSection?.id
                                    || sections.find(s => s.review_status === 'pending')?.id
                                    || sections[0]?.id;
                                if (targetId) {
                                    navigate(`/review/${documentId}/${targetId}`);
                                }
                            } else {
                                setViewMode('page');
                                navigate(`/review/${documentId}`);
                            }
                        }}
                        options={[
                            { value: 'section', label: 'Section view', title: 'Review one parsed leaf at a time' },
                            { value: 'page', label: 'Page view', title: 'Review every leaf that touches a PDF page' },
                        ]}
                    />
                </div>
            </div>

            {viewMode === 'section' && activeSection && (
                <div className="review-infobar">
                    <Breadcrumbs section={activeSection} />
                    <div className="section-facts-bar" aria-label="Section facts">
                        <span className="leaf-index-fact">
                            Leaf{' '}
                            <strong>
                                {currentSectionIndex >= 0 ? currentSectionIndex + 1 : '—'}
                            </strong>{' '}
                            of <strong>{sections.length}</strong>
                            <CopyButton
                                className="btn btn-ghost btn-sm leaf-path-copy"
                                size={12}
                                getText={() => formatLeafJsonPath({
                                    documentName: activeDocument?.name,
                                    section: activeSection,
                                    leafIndex: currentSectionIndex >= 0
                                        ? currentSectionIndex + 1
                                        : null,
                                    leafCount: sections.length,
                                })}
                                label="Copy path"
                                copiedLabel="Copied"
                                title="Copy leaf JSON path"
                                onError={() => pushToast({
                                    type: 'error',
                                    message: 'Copy to clipboard failed',
                                })}
                            />
                        </span>
                        <span>
                            {formatLeafIdentity(
                                activeSection.section_code,
                                activeSection.section_heading,
                            )}
                        </span>
                        <span>
                            Source pages{' '}
                            <strong>
                                {activeSection.start_page}
                                {activeSection.end_page !== activeSection.start_page
                                    ? `–${activeSection.end_page}`
                                    : ''}
                            </strong>
                        </span>
                        <span>
                            <strong>
                                {(activeSection.plain_text || '').length.toLocaleString()}
                            </strong>{' '}
                            extracted characters
                        </span>
                        <span className="shortcut-hint">
                            <kbd>J</kbd>/<kbd>K</kbd> section · <kbd>A</kbd> approve · <kbd>F</kbd> flag · <kbd>[</kbd>/<kbd>]</kbd> page
                        </span>
                    </div>
                </div>
            )}
            {viewMode === 'page' && pageSections.length > 0 && (
                <div className="review-infobar">
                    <Breadcrumbs section={pageSections[0]} />
                </div>
            )}
            <SplitPane left={leftPanel} right={rightPanel} />
        </AppShell>
    );
};

export default ReviewPage;
