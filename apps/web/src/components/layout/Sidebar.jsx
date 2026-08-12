import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Trash2 } from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';
import { useDocumentStore } from '../../stores/documentStore';
import { useReviewStore } from '../../stores/reviewStore';
import { formatHierarchyLabel, formatSectionLabel } from '../../utils/tocLabels';
import { hasCriticalQualityFlags, normalizeQualityFlags } from '../../utils/qualityFlags';
import { sectionWasOcrd } from '../../utils/documentTags';
import { laneLabel } from '../../utils/corpusLanes';
import { editionDateFromName } from '../../utils/editions';

const Sidebar = ({ documentId }) => {
    const navigate = useNavigate();
    const { sidebarTab, setSidebarTab } = useUiStore();
    const { 
        sections,
        activeDocument,
        activeSection, 
        searchResults, 
        search, 
        clearSearch,
        loading 
    } = useDocumentStore();
    const { 
        globalAnnotations, 
        fetchGlobalAnnotations, 
        toggleAnnotationStatus, 
        deleteAnnotation,
        updateAnnotation,
        viewMode,
        setViewMode
    } = useReviewStore();
    const confirmDialog = useUiStore((s) => s.confirmDialog);
    const pushToast = useUiStore((s) => s.pushToast);
    const [localQuery, setLocalQuery] = useState('');
    const [tocQuery, setTocQuery] = useState('');
    const [issuesSubTab, setIssuesSubTab] = useState('open');
    const sidebarRef = useRef(null);

    // A finding whose leaf was rewritten or dropped by a newer JSON version. Its stored
    // offsets no longer locate anything, so it needs a person -- it is not "resolved"
    // and must not be quietly dropped from the list.
    const staleIssues = globalAnnotations.filter(
        a => a.anchor_status === 'needs_recheck' || a.anchor_status === 'orphaned',
    );
    const isStale = a => staleIssues.includes(a);
    const openIssues = globalAnnotations.filter(a => a.status === 'open' && !isStale(a));
    const resolvedIssues = globalAnnotations.filter(a => a.status === 'resolved' && !isStale(a));

    const visibleIssues = issuesSubTab === 'open'
        ? openIssues
        : issuesSubTab === 'resolved'
            ? resolvedIssues
            : staleIssues;

    // Fetch global annotations for document
    useEffect(() => {
        if (documentId) {
            fetchGlobalAnnotations(documentId);
        }
    }, [documentId, fetchGlobalAnnotations]);

    // Trigger debounced search
    useEffect(() => {
        const delay = setTimeout(() => {
            if (localQuery.trim()) {
                search(documentId, localQuery);
            } else {
                clearSearch();
            }
        }, 300);

        return () => clearTimeout(delay);
    }, [localQuery, documentId, search, clearSearch]);

    useEffect(() => {
        const activeNode = sidebarRef.current?.querySelector(
            '.toc-node.level-section.active',
        );
        activeNode?.scrollIntoView({ block: 'center' });
    }, [activeSection?.id, tocQuery, sidebarTab]);

    useEffect(() => {
        const focusFilter = (event) => {
            const tagName = document.activeElement?.tagName;
            const isTyping = ['INPUT', 'TEXTAREA', 'SELECT'].includes(tagName);
            if (event.key === '/' && !isTyping && sidebarTab === 'toc') {
                event.preventDefault();
                sidebarRef.current?.querySelector('#toc-filter')?.focus();
            }
        };
        document.addEventListener('keydown', focusFilter);
        return () => document.removeEventListener('keydown', focusFilter);
    }, [sidebarTab]);

    const handleSectionClick = (secId) => {
        if (viewMode === 'page') {
            setViewMode('section');
        }
        navigate(`/review/${documentId}/${secId}`);
    };

    // Construct TOC tree with headers
    const renderTocTree = () => {
        if (sections.length === 0) {
            return <div className="p-4" style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>No sections found.</div>;
        }

        const normalizedQuery = tocQuery.trim().toLocaleLowerCase();
        const visibleSections = sections.filter((section) => {
            // Skip empty-code / empty-heading leaves (no invented p.N TOC rows).
            if (!formatSectionLabel(section.section_code, section.section_heading, section.start_page)) {
                return false;
            }
            if (!normalizedQuery) return true;
            return [
                section.section_code,
                section.section_heading,
                section.chapter_code,
                section.chapter_heading,
                section.part_code,
                section.part_heading,
                section.division_code,
                section.division_heading,
            ]
                .filter(Boolean)
                .join(' ')
                .toLocaleLowerCase()
                .includes(normalizedQuery);
        });

        let lastChapter = null;
        let lastPart = null;
        let lastDivision = null;
        
        const nodes = [];
        visibleSections.forEach((sec) => {
            if (sec.chapter_code !== lastChapter) {
                lastChapter = sec.chapter_code;
                lastPart = null;
                lastDivision = null;
                const chapterLabel = formatHierarchyLabel(
                    sec.chapter_code,
                    sec.chapter_heading,
                    sec.hierarchy_kind,
                );
                if (chapterLabel) {
                    nodes.push(
                        <div key={`ch-${sec.id}`} className="toc-node level-chapter">
                            {chapterLabel}
                        </div>
                    );
                }
            }
            if (sec.part_code && sec.part_code !== lastPart) {
                lastPart = sec.part_code;
                lastDivision = null;
                const partLabel = formatHierarchyLabel(sec.part_code, sec.part_heading);
                if (partLabel) {
                    nodes.push(
                        <div key={`pt-${sec.id}`} className="toc-node level-part">
                            {partLabel}
                        </div>
                    );
                }
            }
            if (sec.division_code && sec.division_code !== lastDivision) {
                lastDivision = sec.division_code;
                const divisionLabel = formatHierarchyLabel(sec.division_code, sec.division_heading);
                if (divisionLabel) {
                    nodes.push(
                        <div key={`div-${sec.id}`} className="toc-node level-division">
                            {divisionLabel}
                        </div>
                    );
                }
            }

            const isActive = activeSection?.id === sec.id;
            const ocrd = sectionWasOcrd(sec, activeDocument?.provenance?.pages_ocred);
            const qualityFlags = normalizeQualityFlags(sec.quality_flags);
            nodes.push(
                <div 
                    key={`sec-${sec.id}`} 
                    className={`toc-node level-section ${isActive ? 'active' : ''}`}
                    onClick={() => handleSectionClick(sec.id)}
                >
                    <span className="toc-node-status-container">
                        {sec.review_status === 'approved' ? (
                            <span className="toc-status-emoji">✅</span>
                        ) : sec.review_status === 'has_issues' ? (
                            <span
                                className="toc-status-emoji"
                                title={
                                    hasCriticalQualityFlags(sec.quality_flags)
                                        ? 'Auto quality flag'
                                        : 'Reviewer flagged'
                                }
                            >
                                ❌
                            </span>
                        ) : (
                            <span className={`toc-node-status ${sec.review_status || 'pending'}`} />
                        )}
                    </span>
                    <span className="toc-node-label">
                        {formatSectionLabel(sec.section_code, sec.section_heading, sec.start_page)}
                        {ocrd && (
                            <span className="toc-ocr-mark" title="Section spans OCR’d page(s)">
                                OCR
                            </span>
                        )}
                        {qualityFlags.length > 0 && (
                            <span
                                className="toc-quality-mark"
                                title={qualityFlags.map((f) => f.reason || f.code).join('; ')}
                            >
                                QA×{qualityFlags.length}
                            </span>
                        )}
                    </span>
                    {sec.annotation_count > 0 && (
                        <span style={{ fontSize: '0.7rem', padding: '1px 5px', borderRadius: 4, backgroundColor: 'var(--color-error-light)', color: 'var(--color-error)', fontWeight: 700, marginLeft: 'auto', flexShrink: 0 }}>
                            {sec.annotation_count}
                        </span>
                    )}
                </div>
            );
        });

        return (
            <>
                <div className="toc-filter-wrap">
                    <label htmlFor="toc-filter" className="toc-filter">
                        <Search size={15} aria-hidden="true" />
                        <span className="sr-only">Filter sections</span>
                        <input
                            id="toc-filter"
                            type="search"
                            value={tocQuery}
                            onChange={(event) => setTocQuery(event.target.value)}
                            placeholder="Number or heading…"
                            autoComplete="off"
                        />
                    </label>
                    <div className="toc-filter-meta">
                        <span>{visibleSections.length.toLocaleString()} sections</span>
                        <span><kbd>/</kbd> filter · <kbd>J</kbd>/<kbd>K</kbd> move</span>
                    </div>
                </div>
                <div className="toc-tree">
                    {nodes.length > 0 ? nodes : (
                        <div className="toc-empty">No matching sections.</div>
                    )}
                </div>
            </>
        );
    };

    return (
        <div ref={sidebarRef} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Tabs */}
            <div className="toc-tabs">
                {activeDocument && (
                    <div className="toc-lane-header">
                        {laneLabel(activeDocument.corpus_lane
                            || (activeDocument.source_type === 'acts_corpus' ? 'other_acts' : 'manual'))}
                        {editionDateFromName(activeDocument.name).unknown
                            ? ''
                            : ` · ${editionDateFromName(activeDocument.name).label}`}
                    </div>
                )}
                <button 
                    className={`toc-tab ${sidebarTab === 'toc' ? 'active' : ''}`}
                    onClick={() => setSidebarTab('toc')}
                >
                    TOC
                </button>
                <button 
                    className={`toc-tab ${sidebarTab === 'search' ? 'active' : ''}`}
                    onClick={() => setSidebarTab('search')}
                >
                    Search
                </button>
                <button 
                    className={`toc-tab ${sidebarTab === 'annotations' ? 'active' : ''}`}
                    onClick={() => setSidebarTab('annotations')}
                >
                    Notes ({openIssues.length})
                </button>
            </div>

            {/* Content */}
            <div className="toc-content">
                {sidebarTab === 'toc' && (
                    renderTocTree()
                )}

                {sidebarTab === 'search' && (
                    <div className="search-container flex flex-col gap-3">
                        <div className="flex align-center gap-2 p-2" style={{ backgroundColor: 'var(--color-bg-tertiary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)' }}>
                            <Search size={16} style={{ color: 'var(--color-text-muted)' }} />
                            <input 
                                type="text"
                                placeholder="Search section text..."
                                value={localQuery}
                                onChange={(e) => setLocalQuery(e.target.value)}
                                style={{ background: 'transparent', border: 'none', width: '100%', fontSize: '0.85rem', color: 'var(--color-text-primary)' }}
                            />
                        </div>

                        {loading.search && <div className="p-4" style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Searching...</div>}
                        
                        <div className="search-results-list">
                            {!loading.search && searchResults.map(res => (
                                <div 
                                    key={res.section_id} 
                                    className="search-result-card"
                                    onClick={() => handleSectionClick(res.section_id)}
                                >
                                    <div className="search-result-title">
                                        {formatSectionLabel(res.section_code, res.section_heading)}
                                    </div>
                                    <div className="search-result-chapter">
                                        {res.chapter_code || 'Schedules'}
                                    </div>
                                    <div 
                                        className="search-result-snippet"
                                        dangerouslySetInnerHTML={{ __html: res.snippet }}
                                    />
                                </div>
                            ))}
                            {localQuery && !loading.search && searchResults.length === 0 && (
                                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: 12 }}>
                                    No matches found.
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {sidebarTab === 'annotations' && (
                    <div className="annotation-list">
                        <div className="issues-subtabs flex" style={{ padding: '0 8px 12px 8px', gap: 8, borderBottom: '1px solid var(--color-border)' }}>
                            <button
                                className={`btn ${issuesSubTab === 'open' ? 'btn-primary' : 'btn-secondary'}`}
                                style={{ padding: '4px 12px', fontSize: '0.75rem', flex: 1, height: 28 }}
                                onClick={() => setIssuesSubTab('open')}
                            >
                                Open ({openIssues.length})
                            </button>
                            <button
                                className={`btn ${issuesSubTab === 'resolved' ? 'btn-primary' : 'btn-secondary'}`}
                                style={{ padding: '4px 12px', fontSize: '0.75rem', flex: 1, height: 28 }}
                                onClick={() => setIssuesSubTab('resolved')}
                            >
                                Resolved ({resolvedIssues.length})
                            </button>
                            <button
                                className={`btn ${issuesSubTab === 'stale' ? 'btn-primary' : 'btn-secondary'}`}
                                style={{ padding: '4px 12px', fontSize: '0.75rem', flex: 1, height: 28 }}
                                onClick={() => setIssuesSubTab('stale')}
                                title="Findings whose text changed or disappeared in a newer JSON version"
                            >
                                Recheck ({staleIssues.length})
                            </button>
                        </div>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 8px', overflowY: 'auto', flex: 1 }}>
                            {visibleIssues.length === 0 ? (
                                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', padding: 12, textAlign: 'center' }}>
                                    {issuesSubTab === 'stale'
                                        ? 'No notes need rechecking.'
                                        : `No ${issuesSubTab} notes.`}
                                </div>
                            ) : (
                                visibleIssues.map(a => {
                                    const sec = sections.find(s => s.id === a.section_id);
                                    const orphanCode = a.orphan_context?.section_code
                                        || a.orphan_context?.marker;
                                    const sectionLabel = sec
                                        ? `Sec ${sec.section_code}${a.footnote_id ? ' · Footnote' : ''}`
                                        : orphanCode
                                            ? `Sec ${orphanCode} (removed)`
                                            : `Section${a.footnote_id ? ' · Footnote' : ''}`;
                                    
                                    return (
                                        <div 
                                            key={a.id} 
                                            className="annotation-card" 
                                            data-severity={a.severity}
                                            style={{ position: 'relative', cursor: 'pointer', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}
                                            onClick={() => handleSectionClick(a.section_id)}
                                        >
                                            <div className="flex align-center gap-2" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                <input 
                                                    type="checkbox"
                                                    checked={a.status === 'resolved'}
                                                    onChange={(e) => {
                                                        e.stopPropagation();
                                                        toggleAnnotationStatus(a.id, a.status);
                                                    }}
                                                    style={{ cursor: 'pointer', width: 14, height: 14 }}
                                                    title={a.status === 'open' ? "Mark Resolved" : "Re-open"}
                                                />
                                                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-text-secondary)' }}>
                                                    {sectionLabel}
                                                </span>
                                                <button 
                                                    className="annotation-delete-btn" 
                                                    onClick={async (e) => {
                                                        e.stopPropagation();
                                                        const ok = await confirmDialog({
                                                            title: 'Delete note?',
                                                            message: 'Are you sure you want to delete this note?',
                                                            confirmLabel: 'Delete',
                                                        });
                                                        if (ok) deleteAnnotation(a.id);
                                                    }}
                                                    style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center' }}
                                                    title="Delete annotation"
                                                >
                                                    <Trash2 size={12} style={{ color: 'var(--color-text-muted)' }} />
                                                </button>
                                            </div>

                                            {a.anchor_status === 'needs_recheck' && (
                                                <div className="annotation-anchor-warning">
                                                    The text this note pointed at changed in a
                                                    newer JSON version — re-check where it belongs.
                                                    {a.section_id ? (
                                                        <button
                                                            type="button"
                                                            className="btn btn-secondary"
                                                            style={{ marginTop: 8, padding: '4px 8px', fontSize: '0.7rem' }}
                                                            onClick={async (e) => {
                                                                e.stopPropagation();
                                                                try {
                                                                    await updateAnnotation(a.id, {
                                                                        anchorStatus: 'anchored',
                                                                    });
                                                                    pushToast({
                                                                        type: 'info',
                                                                        message: 'Marked as still standing',
                                                                    });
                                                                } catch (err) {
                                                                    pushToast({
                                                                        type: 'error',
                                                                        message: err.message || 'Failed to update note',
                                                                    });
                                                                }
                                                            }}
                                                        >
                                                            Still stands
                                                        </button>
                                                    ) : null}
                                                </div>
                                            )}
                                            {a.anchor_status === 'orphaned' && (
                                                <div className="annotation-anchor-warning">
                                                    The leaf this note pointed at no longer exists
                                                    in the active version. The evidence is kept below.
                                                </div>
                                            )}

                                            <div className="annotation-card-text" style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--color-text-primary)' }}>
                                                "{a.highlighted_text}"
                                            </div>
                                            <div className="annotation-card-description" style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                                                {a.issue_description || 'No description'}
                                            </div>
                                            <div className="annotation-card-meta" style={{ fontSize: '0.7rem', display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-muted)', marginTop: 4 }}>
                                                <span>{a.reviewer_name || 'QA'}</span>
                                                <span>{new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Sidebar;
