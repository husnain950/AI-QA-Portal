import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, AlertCircle, CheckCircle, History } from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import Sidebar from '../components/layout/Sidebar';
import SplitPane from '../components/review/SplitPane';
import PdfPanel from '../components/review/PdfPanel';
import HtmlPanel from '../components/review/HtmlPanel';
import ReviewToolbar from '../components/review/ReviewToolbar';
import NewVersionButton from '../components/review/NewVersionButton';
import Breadcrumbs from '../components/review/Breadcrumbs';

import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useKeyboardNav } from '../hooks/useKeyboardNav';
import { api } from '../utils/api';
import VersionPanel from '../components/review/VersionPanel';
import { formatLeafIdentity } from '../utils/tocLabels';

const ReviewPage = () => {
    const { documentId, sectionId } = useParams();
    const navigate = useNavigate();

    const [successMessage, setSuccessMessage] = useState('');
    const [versionsOpen, setVersionsOpen] = useState(false);

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
    const [initialLoad, setInitialLoad] = useState(true);
    const [error, setError] = useState('');
    const currentSectionIndex = sections.findIndex(
        (section) => section.id === activeSection?.id,
    );

    const navigateBySection = (offset) => {
        if (viewMode !== 'section' || currentSectionIndex < 0) return;
        const target = sections[currentSectionIndex + offset];
        if (target) {
            navigate(`/review/${documentId}/${target.id}`);
        }
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

                // Fetch sections list for TOC
                await fetchSections(documentId);
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
    }, [documentId, fetchDocument, fetchSections]);

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
            <div className="flex flex-col justify-center align-center" style={{ height: '100vh', gap: 16 }}>
                <Loader2 className="animate-spin" size={32} style={{ color: 'var(--color-accent)' }} />
                <span style={{ fontSize: '0.9rem', color: 'var(--color-text-secondary)' }}>Loading Workspace...</span>
            </div>
        );
    }

    if (error || !activeDocument) {
        return (
            <div className="flex flex-col justify-center align-center" style={{ height: '100vh', gap: 16 }}>
                <AlertCircle size={48} style={{ color: 'var(--color-error)' }} />
                <h3>Workspace Error</h3>
                <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>{error || 'Document metadata could not be fetched'}</p>
                <button className="btn btn-primary" onClick={() => navigate('/library')}>
                    <ArrowLeft size={16} />
                    <span>Back to Dashboard</span>
                </button>
            </div>
        );
    }

    const pdfUrl = api.getFileUrl(activeDocument.pdf_filename);

    const leftPanel = (
        <PdfPanel pdfUrl={pdfUrl} />
    );

    const rightPanel = (
        <div className="flex flex-col height-100" style={{ height: '100%' }}>
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
                        <div className="flex justify-center align-center" style={{ height: '100%', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                            Select a section from the Table of Contents to begin review
                        </div>
                    )
                ) : (
                    /* Page View: list of sections covering current page */
                    pageSections.length > 0 ? (
                        <div style={{ flex: 1, overflowY: 'auto' }}>
                            {pageSections.map(sec => (
                                <div key={sec.id} style={{ borderBottom: '4px solid var(--color-border)', paddingBottom: 24 }}>
                                    <div style={{ padding: '12px 24px', backgroundColor: 'var(--color-bg-tertiary)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                                            Section {sec.section_code}: {sec.section_heading}
                                        </span>
                                        <span className={`badge badge-${sec.review_status}`}>
                                            {sec.review_status}
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
                        <div className="flex justify-center align-center" style={{ height: '100%', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                            No parsed sections map to page {currentPage}
                        </div>
                    )
                )}
            </div>
            {viewMode === 'section' && <ReviewToolbar />}
        </div>
    );

    const statsText = activeDocument.stats
        ? (() => {
            const flagged = activeDocument.stats.flagged_sections
                ?? activeDocument.stats.has_issues
                ?? 0;
            const openNotes = activeDocument.stats.open_annotations ?? 0;
            return `(${activeDocument.stats.approved}/${activeDocument.total_sections} approved · ${flagged} flagged · ${openNotes} open notes)`;
        })()
        : '';

    const actions = (
        <div className="review-header-actions flex align-center gap-3">
            {/* Available for every document now: ACT-corpus rows used to be locked out
                because a replacement overwrote the parse in place. Versions make it
                reversible, and sync_acts still reconciles by content hash. */}
            <NewVersionButton
                documentId={documentId}
                documentName={activeDocument?.name}
                className="replace-json-action btn btn-secondary"
                style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6 }}
                onSuccess={async () => {
                    navigate(`/review/${documentId}`, { replace: true });
                    await fetchDocument(documentId);
                    await fetchSections(documentId);
                    setSuccessMessage('New JSON version is active. Open Versions to see what changed.');
                    setVersionsOpen(true);
                    setTimeout(() => setSuccessMessage(''), 6000);
                }}
            />

            <button
                className="versions-action btn btn-secondary"
                style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 6 }}
                onClick={() => setVersionsOpen((open) => !open)}
                title="Version history, diffs and rollback"
            >
                <History size={14} />
                <span>Versions</span>
            </button>

            <div className="flex align-center gap-2">
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>View:</span>
                <div className="flex" style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                    <button
                        className={`btn ${viewMode === 'section' ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', fontSize: '0.75rem', borderRadius: 0, border: 'none' }}
                        onClick={() => {
                            setViewMode('section');
                            const targetId = activeSection?.id || sections.find(s => s.review_status === 'pending')?.id || sections[0]?.id;
                            if (targetId) {
                                navigate(`/review/${documentId}/${targetId}`);
                            }
                        }}
                    >
                        Section View
                    </button>
                    <button
                        className={`btn ${viewMode === 'page' ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 12px', fontSize: '0.75rem', borderRadius: 0, border: 'none' }}
                        onClick={() => {
                            setViewMode('page');
                            navigate(`/review/${documentId}`);
                        }}
                    >
                        Page View
                    </button>
                </div>
            </div>
        </div>
    );

    return (
        <AppShell 
            title={`${activeDocument.name} ${statsText}`}
            showBackButton={true}
            sidebarContent={<Sidebar documentId={documentId} />}
            actions={actions}
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

            {successMessage && (
                <div className="flex align-center gap-2 p-3" style={{ 
                    backgroundColor: 'var(--color-success-light)', 
                    color: 'var(--color-success)', 
                    borderBottom: '1px solid var(--color-success)', 
                    padding: '10px 24px', 
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center'
                }}>
                    <CheckCircle size={16} />
                    <span>{successMessage}</span>
                </div>
            )}

            {viewMode === 'section' && activeSection && (
                <>
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
                            <kbd>J</kbd>/<kbd>K</kbd> section · <kbd>[</kbd>/<kbd>]</kbd> page
                        </span>
                    </div>
                </>
            )}
            {viewMode === 'page' && pageSections.length > 0 && (
                <Breadcrumbs section={pageSections[0]} />
            )}
            <SplitPane left={leftPanel} right={rightPanel} />
        </AppShell>
    );
};

export default ReviewPage;
