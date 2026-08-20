import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Trash2, CheckCircle2, XCircle } from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';
import { useDocumentStore } from '../../stores/documentStore';
import { useReviewStore } from '../../stores/reviewStore';
import { formatHierarchyLabel, formatSectionLabel } from '../../utils/tocLabels';
import { hasCriticalQualityFlags, normalizeQualityFlags } from '../../utils/qualityFlags';
import { sectionWasOcrd } from '../../utils/documentTags';
import { laneLabel } from '../../utils/corpusLanes';
import { editionDateFromName } from '../../utils/editions';

const SearchSnippet = ({ result }) => {
    const text = result.snippet_text ?? result.snippet ?? '';
    const ranges = [...(result.match_ranges || [])]
        .filter((range) => Number.isInteger(range.start) && Number.isInteger(range.end))
        .sort((a, b) => a.start - b.start);
    if (!ranges.length) return <div className="search-result-snippet">{text}</div>;
    const parts = [];
    let cursor = 0;
    ranges.forEach((range, index) => {
        const start = Math.max(cursor, Math.min(text.length, range.start));
        const end = Math.max(start, Math.min(text.length, range.end));
        if (start > cursor) parts.push(text.slice(cursor, start));
        if (end > start) parts.push(<mark key={`match-${index}`}>{text.slice(start, end)}</mark>);
        cursor = end;
    });
    if (cursor < text.length) parts.push(text.slice(cursor));
    return <div className="search-result-snippet">{parts}</div>;
};

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
            return <div className="toc-empty">No sections found.</div>;
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
                        {sec.review_status === 'approved' || sec.review_status === 'approved_inherited' ? (
                            <span className="toc-status-icon is-approved" title="Approved">
                                <CheckCircle2 size={13} aria-hidden="true" />
                            </span>
                        ) : sec.review_status === 'has_issues' ? (
                            <span
                                className="toc-status-icon is-flagged"
                                title={
                                    hasCriticalQualityFlags(sec.quality_flags)
                                        ? 'Auto quality flag'
                                        : 'Reviewer flagged'
                                }
                            >
                                <XCircle size={13} aria-hidden="true" />
                            </span>
                        ) : (
                            <span className={`toc-node-status ${sec.review_status || 'pending'}`} title="Pending" />
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
                        <span className="toc-annotation-count" title={`${sec.annotation_count} open notes`}>
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
        <div ref={sidebarRef} className="sidebar-inner">
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
                        <label className="sidebar-search-box" htmlFor="sidebar-search-input">
                            <Search size={15} aria-hidden="true" />
                            <span className="sr-only">Search section text</span>
                            <input
                                id="sidebar-search-input"
                                type="search"
                                placeholder="Search section text…"
                                value={localQuery}
                                onChange={(e) => setLocalQuery(e.target.value)}
                            />
                        </label>

                        {loading.search && <div className="sidebar-muted-note">Searching…</div>}

                        <div className="search-results-list">
                            {!loading.search && searchResults.map(res => (
                                <button
                                    type="button"
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
                                    <SearchSnippet result={res} />
                                </button>
                            ))}
                            {localQuery && !loading.search && searchResults.length === 0 && (
                                <div className="sidebar-muted-note" style={{ textAlign: 'center' }}>
                                    No matches found.
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {sidebarTab === 'annotations' && (
                    <div className="annotation-list">
                        <div className="issues-subtabs">
                            <button
                                className={`issues-subtab ${issuesSubTab === 'open' ? 'active' : ''}`}
                                onClick={() => setIssuesSubTab('open')}
                                aria-pressed={issuesSubTab === 'open'}
                            >
                                Open ({openIssues.length})
                            </button>
                            <button
                                className={`issues-subtab ${issuesSubTab === 'resolved' ? 'active' : ''}`}
                                onClick={() => setIssuesSubTab('resolved')}
                                aria-pressed={issuesSubTab === 'resolved'}
                            >
                                Resolved ({resolvedIssues.length})
                            </button>
                            <button
                                className={`issues-subtab ${issuesSubTab === 'stale' ? 'active' : ''}`}
                                onClick={() => setIssuesSubTab('stale')}
                                aria-pressed={issuesSubTab === 'stale'}
                                title="Findings whose text changed or disappeared in a newer JSON version"
                            >
                                Recheck ({staleIssues.length})
                            </button>
                        </div>

                        <div className="annotation-cards">
                            {visibleIssues.length === 0 ? (
                                <div className="sidebar-muted-note" style={{ textAlign: 'center' }}>
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
                                            onClick={() => handleSectionClick(a.section_id)}
                                        >
                                            <div className="annotation-card-head">
                                                <input
                                                    type="checkbox"
                                                    checked={a.status === 'resolved'}
                                                    onChange={(e) => {
                                                        e.stopPropagation();
                                                        toggleAnnotationStatus(a.id, a.status);
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                    title={a.status === 'open' ? 'Mark resolved' : 'Re-open'}
                                                    aria-label={a.status === 'open' ? 'Mark resolved' : 'Re-open'}
                                                />
                                                <span className="annotation-card-section">
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
                                                    title="Delete note"
                                                    aria-label="Delete note"
                                                >
                                                    <Trash2 size={12} />
                                                </button>
                                            </div>

                                            {a.anchor_status === 'needs_recheck' && (
                                                <div className="annotation-anchor-warning">
                                                    The text this note pointed at changed in a
                                                    newer JSON version — re-check where it belongs.
                                                    {a.section_id ? (
                                                        <button
                                                            type="button"
                                                            className="btn btn-xs btn-secondary"
                                                            style={{ marginTop: 8 }}
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

                                            <div className="annotation-card-text">
                                                "{a.highlighted_text}"
                                            </div>
                                            <div className="annotation-card-description">
                                                {a.issue_description || 'No description'}
                                            </div>
                                            <div className="annotation-card-meta">
                                                <span>{a.reviewer_name || 'QA'}</span>
                                                <span title={new Date(a.created_at).toLocaleString()}>
                                                    {new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                </span>
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
