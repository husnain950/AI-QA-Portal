import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, AlertCircle, History, GitBranch } from 'lucide-react';

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

import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useAiFixStore } from '../stores/aiFixStore';
import { useUiStore } from '../stores/uiStore';
import { useKeyboardNav } from '../hooks/useKeyboardNav';
import { api, versionsApi } from '../utils/api';
import VersionPanel from '../components/review/VersionPanel';
import { formatLeafIdentity } from '../utils/tocLabels';
import { TAG_NEEDS_REVIEW, TAG_PROVISIONAL } from '../utils/documentTags';
import { laneLabel } from '../utils/corpusLanes';
import { editionDateFromName, familyKeyFromName } from '../utils/editions';

const ReviewPage = () => {
    const { documentId, sectionId } = useParams();
    const navigate = useNavigate();

    const [versionsOpen, setVersionsOpen] = useState(false);
    const [editions, setEditions] = useState(null);
    const pushToast = useUiStore((s) => s.pushToast);

    const {
        activeDocument,
        sections,
        activeSection,
        pageSections,
        fetchDocument,
        fetchSections,
        fetchSection,
        fetchSectionsByPage,
    } = useDocumentStore();

    const { currentPage, viewMode, setViewMode, setCurrentPage } = useReviewStore();
    const fetchAiProposals = useAiFixStore((s) => s.fetchProposals);
    const [initialLoad, setInitialLoad] = useState(true);
    const [error, setError] = useState('');
    const currentSectionIndex = sections.findIndex(
        (section) => section.id === activeSection?.id,
    );

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
    const edition = editionDateFromName(activeDocument.name);
    const lane = activeDocument.corpus_lane
        || (activeDocument.source_type === 'acts_corpus' ? 'other_acts' : 'manual');
    const familyKey = familyKeyFromName(activeDocument.name);

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
                onChanged={async () => {
                    await fetchDocument(documentId);
                    await fetchSections(documentId);
                }}
            />

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
                            <span className="progress-bar" aria-hidden="true">
                                <span
                                    className={`progress-bar-fill ${progressPct === 100 ? 'is-complete' : ''}`}
                                    style={{ width: `${progressPct}%` }}
                                />
                            </span>
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
                    {activeSection?.section_code && (
                        <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            title="Open family timeline for this section"
                            onClick={() => navigate(
                                `/timeline/${encodeURIComponent(familyKey)}/${encodeURIComponent(activeSection.section_code)}`,
                            )}
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
                        <span>
                            Leaf{' '}
                            <strong>
                                {currentSectionIndex >= 0 ? currentSectionIndex + 1 : '—'}
                            </strong>{' '}
                            of <strong>{sections.length}</strong>
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
