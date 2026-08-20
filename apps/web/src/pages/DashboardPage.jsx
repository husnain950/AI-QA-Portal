import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    UploadCloud, FileText, Trash2, Download, Loader2, Search,
    RefreshCw, Database, AlertTriangle, LayoutGrid, Rows3, Upload, ChevronDown,
} from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import NewVersionButton from '../components/review/NewVersionButton';
import DropdownMenu from '../components/ui/DropdownMenu';
import EmptyState from '../components/ui/EmptyState';
import Skeleton from '../components/ui/Skeleton';
import SegmentedControl from '../components/ui/SegmentedControl';
import { useDocumentStore } from '../stores/documentStore';
import DocumentHealth from '../components/dashboard/DocumentHealth';
import DocumentTags from '../components/dashboard/DocumentTags';
import { api, corpusApi } from '../utils/api';
import { facetCounts, filterDocuments, groupDocumentsByFamily } from '../utils/documentFilters';
import { LANE_ORDER, documentLane, laneLabel } from '../utils/corpusLanes';
import { CORPUS_MOUNT_HINT, describeCorpusSync } from '../utils/corpusStatus';
import { editionDateFromName } from '../utils/editions';
import { useUiStore } from '../stores/uiStore';

const EMPTY_FACETS = {
    corpusLane: '',
    sourceKind: '',
    health: '',
    review: '',
    flagged: '',
};

const VIEW_KEY = 'qa-portal-library-view';

function timeAgo(iso) {
    if (!iso) return null;
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

/** Row-level actions shared by list and card layouts. */
function DocumentActions({ doc, onDelete, onExport, onNewVersion }) {
    const newVersionTrigger = useRef(null);
    return (
        <div className="doc-actions" onClick={(e) => e.stopPropagation()}>
            <NewVersionButton
                documentId={doc.id}
                documentName={doc.name}
                hideButton
                triggerRef={newVersionTrigger}
                onSuccess={onNewVersion}
            />
            <DropdownMenu
                ariaLabel={`Actions for ${doc.name}`}
                items={[
                    { key: 'json', label: 'Export report (JSON)', icon: Download, onSelect: () => onExport(doc.id, 'json') },
                    { key: 'csv', label: 'Export report (CSV)', icon: Download, onSelect: () => onExport(doc.id, 'csv') },
                    {
                        key: 'version',
                        label: 'Upload new JSON version…',
                        icon: Upload,
                        title: 'Add a new JSON version (the PDF stays as it is)',
                        onSelect: () => newVersionTrigger.current?.(),
                    },
                    { type: 'separator' },
                    { key: 'delete', label: 'Delete document…', icon: Trash2, danger: true, onSelect: () => onDelete(doc.id, doc.name) },
                ]}
            />
        </div>
    );
}

const DashboardPage = () => {
    const navigate = useNavigate();
    const { documents, documentsError, fetchDocuments, deleteDocument, loading } = useDocumentStore();
    const pushToast = useUiStore((s) => s.pushToast);
    const confirmDialog = useUiStore((s) => s.confirmDialog);

    const [documentQuery, setDocumentQuery] = useState('');
    const [facets, setFacets] = useState(EMPTY_FACETS);
    const [sort, setSort] = useState('name');
    const [layout, setLayout] = useState(() => {
        try {
            return window.localStorage?.getItem(VIEW_KEY) || 'list';
        } catch {
            return 'list';
        }
    });
    const [corpusStatus, setCorpusStatus] = useState(null);
    const [syncing, setSyncing] = useState(false);
    const [collapsedFamilies, setCollapsedFamilies] = useState(() => new Set());
    const syncMeta = corpusStatus ? describeCorpusSync(corpusStatus) : null;
    const mountsUnavailable = Boolean(syncMeta && !syncMeta.canSync);

    const setFacet = (key, value) => {
        setFacets((prev) => ({ ...prev, [key]: value }));
    };

    const setLayoutPersisted = (value) => {
        setLayout(value);
        try {
            window.localStorage?.setItem(VIEW_KEY, value);
        } catch {
            // localStorage unavailable
        }
    };

    const refreshCorpusStatus = useCallback(async () => {
        try {
            const status = await corpusApi.status();
            setCorpusStatus(status);
        } catch {
            setCorpusStatus(null);
        }
    }, []);

    useEffect(() => {
        fetchDocuments();
        refreshCorpusStatus();
    }, [fetchDocuments, refreshCorpusStatus]);

    const handleCorpusSync = async () => {
        try {
            setSyncing(true);
            const summary = await corpusApi.sync({ metrics: true });
            const ord = summary.ordinance || {};
            const acts = summary.acts || {};
            pushToast({
                type: 'success',
                message: `Corpus sync finished — Ordinance imported ${ord.imported ?? 0} / skipped ${ord.skipped ?? 0}; `
                    + `Acts imported ${acts.imported ?? 0} / skipped ${acts.skipped ?? 0}.`,
            });
            await fetchDocuments();
            await refreshCorpusStatus();
        } catch (err) {
            pushToast({ type: 'error', message: 'Corpus sync failed: ' + (err.message || 'Unknown error') });
        } finally {
            setSyncing(false);
        }
    };

    const handleDelete = async (docId, name) => {
        const ok = await confirmDialog({
            title: 'Delete document?',
            message: `Delete "${name}"? This removes annotations, footnotes validation, and source files.`,
            confirmLabel: 'Delete',
        });
        if (!ok) return;
        try {
            await deleteDocument(docId);
            pushToast({ type: 'success', message: `Deleted "${name}"` });
        } catch (err) {
            pushToast({ type: 'error', message: 'Failed to delete document: ' + err.message });
        }
    };

    const handleExport = (docId, format) => {
        window.open(api.getDownloadUrl(`/documents/${docId}/export?format=${format}`));
    };

    const handleNewVersion = useCallback(async () => {
        pushToast({ type: 'success', message: 'New JSON version is active. Open the document to see what changed.' });
        fetchDocuments();
    }, [pushToast, fetchDocuments]);

    const handleReviewClick = (docId) => {
        navigate(`/review/${docId}`);
    };

    // Aggregated metrics
    const totalDocs = documents.length;
    const totalSections = documents.reduce((sum, doc) => sum + doc.total_sections, 0);
    const totalIssues = documents.reduce((sum, doc) => sum + (doc.stats?.has_issues || 0), 0);
    const totalReviewed = documents.reduce((sum, doc) => sum + (doc.stats?.reviewed || 0), 0);
    const overallCompletion = totalSections > 0 ? Math.round((totalReviewed / totalSections) * 100) : 0;
    const counts = useMemo(() => facetCounts(documents), [documents]);
    const filteredDocuments = useMemo(
        () => filterDocuments(documents, { query: documentQuery, facets, sort }),
        [documents, documentQuery, facets, sort],
    );
    const familyGroups = useMemo(
        () => groupDocumentsByFamily(filteredDocuments, sort),
        [filteredDocuments, sort],
    );
    const facetsActive = Boolean(
        facets.corpusLane || facets.sourceKind || facets.health || facets.review
        || facets.flagged || documentQuery.trim(),
    );

    const clearFilters = () => {
        setFacets(EMPTY_FACETS);
        setDocumentQuery('');
    };

    const toggleFamily = (familyKey) => {
        setCollapsedFamilies((prev) => {
            const next = new Set(prev);
            if (next.has(familyKey)) next.delete(familyKey);
            else next.add(familyKey);
            return next;
        });
    };

    const FacetGroup = ({ label, ariaLabel, value, onChange, options }) => (
        <div className="facet-group" role="group" aria-label={ariaLabel || label}>
            <span className="facet-label">{label}</span>
            <div className="source-filters">
                {options.map(([optionValue, optionLabel]) => (
                    <button
                        key={optionValue || 'all'}
                        type="button"
                        className={`source-filter ${value === optionValue ? 'active' : ''}`}
                        onClick={() => onChange(optionValue)}
                        aria-pressed={value === optionValue}
                    >
                        {optionLabel}
                    </button>
                ))}
            </div>
        </div>
    );

    const docCompletion = (doc) => {
        const reviewedCount = doc.stats?.reviewed || 0;
        const totalCount = doc.total_sections;
        return totalCount > 0 ? Math.round((reviewedCount / totalCount) * 100) : 0;
    };

    const renderDocumentRow = (doc) => {
        const compPercent = docCompletion(doc);
        const edition = editionDateFromName(doc.name);
        const lane = documentLane(doc);
        const flaggedCount = doc.stats?.has_issues || 0;

        return (
            <div
                key={doc.id}
                className="doc-row"
                onClick={() => handleReviewClick(doc.id)}
                role="link"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') handleReviewClick(doc.id);
                }}
            >
                <div className="doc-row-main">
                    <div className="doc-row-title">
                        <span className={`source-badge lane-${lane}`}>{laneLabel(lane)}</span>
                        {!edition.unknown && (
                            <span className="edition-year-badge" title="Edition year">{edition.label}</span>
                        )}
                        <h3 className="doc-row-name" title={doc.name}>{doc.name}</h3>
                        <DocumentTags provenance={doc.provenance} compact />
                    </div>
                    <div className="doc-row-meta">
                        <span>{doc.total_sections.toLocaleString()} sections</span>
                        <span>{doc.total_pages} pages</span>
                        <span title="JSON versions of this parse (the PDF is fixed)">
                            {doc.version_count ?? 1} version{(doc.version_count ?? 1) === 1 ? '' : 's'}
                        </span>
                        {flaggedCount > 0 && (
                            <span className="doc-row-flagged" title={`${flaggedCount} flagged sections`}>
                                <AlertTriangle size={11} aria-hidden="true" />
                                {flaggedCount} flagged
                            </span>
                        )}
                        <DocumentHealth health={doc.health} />
                    </div>
                </div>
                <div className="doc-row-progress" title={`${doc.stats?.reviewed || 0} of ${doc.total_sections} sections reviewed`}>
                    <span className="progress-bar">
                        <span
                            className={`progress-bar-fill ${compPercent === 100 ? 'is-complete' : ''}`}
                            style={{ width: `${compPercent}%` }}
                        />
                    </span>
                    <span className="doc-row-percent">{compPercent}%</span>
                </div>
                <div className="doc-row-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => handleReviewClick(doc.id)}
                    >
                        {compPercent === 0 ? 'Start review' : 'Continue'}
                    </button>
                    <DocumentActions
                        doc={doc}
                        onDelete={handleDelete}
                        onExport={handleExport}
                        onNewVersion={handleNewVersion}
                    />
                </div>
            </div>
        );
    };

    const renderDocumentCard = (doc) => {
        const compPercent = docCompletion(doc);
        const edition = editionDateFromName(doc.name);
        const lane = documentLane(doc);
        const flaggedCount = doc.stats?.has_issues || 0;

        return (
            <div
                key={doc.id}
                className="document-card"
                onClick={() => handleReviewClick(doc.id)}
                role="link"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') handleReviewClick(doc.id);
                }}
            >
                <div className="document-card-head">
                    <span className={`source-badge lane-${lane}`}>{laneLabel(lane)}</span>
                    {!edition.unknown && (
                        <span className="edition-year-badge" title="Edition year">{edition.label}</span>
                    )}
                    <DocumentTags provenance={doc.provenance} compact />
                    <DocumentActions
                        doc={doc}
                        onDelete={handleDelete}
                        onExport={handleExport}
                        onNewVersion={handleNewVersion}
                    />
                </div>
                <h3 className="document-name" title={doc.name}>{doc.name}</h3>
                <div className="document-card-stats">
                    <span>{doc.total_sections.toLocaleString()} sections</span>
                    <span>{doc.total_pages} pages</span>
                    <span>{doc.version_count ?? 1} version{(doc.version_count ?? 1) === 1 ? '' : 's'}</span>
                    {flaggedCount > 0 && (
                        <span className="doc-row-flagged">
                            <AlertTriangle size={11} aria-hidden="true" />
                            {flaggedCount} flagged
                        </span>
                    )}
                </div>
                <DocumentHealth health={doc.health} />
                <div className="document-card-footer">
                    <div className="doc-row-progress" title={`${doc.stats?.reviewed || 0} of ${doc.total_sections} sections reviewed`}>
                        <span className="progress-bar">
                            <span
                                className={`progress-bar-fill ${compPercent === 100 ? 'is-complete' : ''}`}
                                style={{ width: `${compPercent}%` }}
                            />
                        </span>
                        <span className="doc-row-percent">{compPercent}%</span>
                    </div>
                    <button
                        className="btn btn-sm btn-primary"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleReviewClick(doc.id);
                        }}
                    >
                        {compPercent === 0 ? 'Start review' : 'Continue'}
                    </button>
                </div>
            </div>
        );
    };

    const renderDocuments = (docs) => (
        layout === 'list'
            ? <div className="doc-rows">{docs.map((doc) => renderDocumentRow(doc))}</div>
            : <div className="document-grid">{docs.map((doc) => renderDocumentCard(doc))}</div>
    );

    return (
        <AppShell title="Library" scrollable>
            <div className="dashboard-container">
                <header className="library-header">
                    <div className="library-header-text">
                        <h1>Library</h1>
                        <p>
                            {totalDocs.toLocaleString()} documents · {totalSections.toLocaleString()} sections
                            {syncMeta && (
                                <span className="library-sync-meta" title={CORPUS_MOUNT_HINT}>
                                    <Database size={12} aria-hidden="true" />
                                    {syncMeta.syncKind === 'recorded' ? (
                                        <>
                                            last sync{' '}
                                            <span
                                                className={syncMeta.lastStatus === 'ok'
                                                    ? 'sync-status-ok'
                                                    : 'sync-status-warn'}
                                            >
                                                {syncMeta.lastStatus || 'unknown'}
                                            </span>{' '}
                                            <span title={new Date(syncMeta.lastSyncAt).toLocaleString()}>
                                                {timeAgo(syncMeta.lastSyncAt)}
                                            </span>
                                        </>
                                    ) : (
                                        syncMeta.syncLabel
                                    )}
                                    {' · '}
                                    {syncMeta.mountsLabel}
                                </span>
                            )}
                        </p>
                    </div>
                    <div className="library-header-actions">
                        <button
                            className="btn btn-secondary"
                            onClick={handleCorpusSync}
                            disabled={syncing || corpusStatus?.sync_running || mountsUnavailable}
                            title={mountsUnavailable
                                ? 'Pipeline mounts are not on this host — upload PDF+JSON or bake a seed image'
                                : 'Sync Ordinance + Acts from configured corpus mounts'}
                        >
                            {syncing || corpusStatus?.sync_running ? (
                                <Loader2 size={15} className="animate-spin" />
                            ) : (
                                <RefreshCw size={15} />
                            )}
                            <span>{syncing ? 'Syncing…' : 'Sync corpus'}</span>
                        </button>
                        <button className="btn btn-primary" onClick={() => navigate('/upload')}>
                            <UploadCloud size={15} />
                            <span>Upload document</span>
                        </button>
                    </div>
                </header>

                <section className="stats-grid">
                    <button
                        type="button"
                        className={`stat-card ${!facetsActive ? '' : 'stat-card-dim'}`}
                        onClick={clearFilters}
                        title="Show all documents"
                    >
                        <div className="stat-value">{totalDocs}</div>
                        <div className="stat-label">Documents</div>
                    </button>
                    <div className="stat-card stat-card-static">
                        <div className="stat-value">{totalSections.toLocaleString()}</div>
                        <div className="stat-label">Total sections</div>
                    </div>
                    <button
                        type="button"
                        className={`stat-card ${facets.flagged ? 'stat-card-active' : ''}`}
                        onClick={() => setFacet('flagged', facets.flagged ? '' : 'flagged')}
                        title="Show only documents with flagged sections"
                        aria-pressed={Boolean(facets.flagged)}
                    >
                        <div className="stat-value" style={{ color: totalIssues > 0 ? 'var(--color-warning)' : 'inherit' }}>
                            {totalIssues}
                        </div>
                        <div className="stat-label">Flagged sections</div>
                    </button>
                    <button
                        type="button"
                        className={`stat-card ${facets.review === 'in_progress' ? 'stat-card-active' : ''}`}
                        onClick={() => setFacet('review', facets.review === 'in_progress' ? '' : 'in_progress')}
                        title="Show documents still in progress"
                        aria-pressed={facets.review === 'in_progress'}
                    >
                        <div className="stat-value" style={{ color: 'var(--color-success)' }}>
                            {overallCompletion}%
                        </div>
                        <div className="stat-label">Overall completion</div>
                    </button>
                </section>

                <section className="library-controls-row">
                    <label className="document-search" htmlFor="document-filter">
                        <Search size={15} aria-hidden="true" />
                        <span className="sr-only">Filter documents</span>
                        <input
                            id="document-filter"
                            type="search"
                            value={documentQuery}
                            onChange={(event) => setDocumentQuery(event.target.value)}
                            placeholder="Find an Act or edition…"
                            autoComplete="off"
                        />
                    </label>
                    <span className="library-result-count">
                        {filteredDocuments.length.toLocaleString()} of {documents.length.toLocaleString()}
                        {` · ${familyGroups.length} famil${familyGroups.length === 1 ? 'y' : 'ies'}`}
                    </span>
                    <SegmentedControl
                        ariaLabel="Library layout"
                        value={layout}
                        onChange={setLayoutPersisted}
                        options={[
                            { value: 'list', label: 'List', icon: <Rows3 size={13} /> },
                            { value: 'cards', label: 'Cards', icon: <LayoutGrid size={13} /> },
                        ]}
                    />
                    <label className="library-sort" htmlFor="document-sort">
                        <span className="sr-only">Sort documents</span>
                        <select
                            id="document-sort"
                            className="ui-select"
                            value={sort}
                            onChange={(event) => setSort(event.target.value)}
                        >
                            <option value="name">Sort: Name</option>
                            <option value="newest">Sort: Newest</option>
                            <option value="pages">Sort: Pages</option>
                            <option value="health">Sort: Health</option>
                            <option value="completion">Sort: Completion</option>
                        </select>
                    </label>
                </section>

                <section className="library-facets library-facets-sticky" aria-label="Document facets">
                    <FacetGroup
                        label="Source"
                        value={facets.corpusLane}
                        onChange={(value) => setFacet('corpusLane', value)}
                        options={[
                            ['', `All ${counts.total}`],
                            ...LANE_ORDER
                                .filter((lane) => (counts.lanes[lane] || 0) > 0)
                                .map((lane) => [lane, `${laneLabel(lane)} ${counts.lanes[lane]}`]),
                        ]}
                    />
                    <FacetGroup
                        label="Kind"
                        value={facets.sourceKind}
                        onChange={(value) => setFacet('sourceKind', value)}
                        options={[
                            ['', 'All'],
                            ['native-digital', `Native ${counts.kinds['native-digital'] || 0}`],
                            ['scanned-ocr', `Scanned ${counts.kinds['scanned-ocr'] || 0}`],
                            ['mixed-ocr', `Mixed ${counts.kinds['mixed-ocr'] || 0}`],
                        ]}
                    />
                    <FacetGroup
                        label="Health"
                        value={facets.health}
                        onChange={(value) => setFacet('health', value)}
                        options={[
                            ['', 'All'],
                            ['within_gate', `Within gate ${counts.health.within_gate || 0}`],
                            ['outside_gate', `Outside gate ${counts.health.outside_gate || 0}`],
                            ['unmeasured', `Unmeasured ${counts.health.unmeasured || 0}`],
                        ]}
                    />
                    <FacetGroup
                        label="Review"
                        value={facets.review}
                        onChange={(value) => setFacet('review', value)}
                        options={[
                            ['', 'All'],
                            ['complete', `Complete ${counts.review.complete || 0}`],
                            ['in_progress', `In progress ${counts.review.in_progress || 0}`],
                            ['untouched', `Untouched ${counts.review.untouched || 0}`],
                        ]}
                    />
                    {facetsActive && (
                        <button
                            type="button"
                            className="btn btn-sm btn-secondary facet-clear"
                            onClick={clearFilters}
                        >
                            Clear filters
                        </button>
                    )}
                </section>

                {loading.documents ? (
                    <div className="doc-rows" aria-label="Loading documents">
                        {[...Array(5)].map((_, i) => (
                            <div key={i} className="doc-row doc-row-skeleton">
                                <div className="doc-row-main">
                                    <Skeleton width={`${50 - (i % 3) * 8}%`} height={15} />
                                    <Skeleton width={`${34 - (i % 2) * 6}%`} height={11} />
                                </div>
                                <Skeleton width={120} height={10} />
                                <Skeleton width={90} height={26} />
                            </div>
                        ))}
                    </div>
                ) : documentsError ? (
                    <EmptyState
                        icon={<AlertTriangle size={44} />}
                        title="Couldn't load the corpus"
                        message={`The API didn't respond (${documentsError}). This is a load failure, not an empty corpus — the documents are still there.`}
                    >
                        <button className="btn btn-primary" onClick={fetchDocuments}>
                            <RefreshCw size={15} />
                            <span>Retry</span>
                        </button>
                    </EmptyState>
                ) : documents.length === 0 ? (
                    <EmptyState
                        icon={<FileText size={44} />}
                        title="Corpus is empty"
                        message="Seed from the configured Ordinance + Acts pipeline output, then review side-by-side. Closed loop: convert → sync → review → export QA → import findings."
                    >
                        <button
                            className="btn btn-primary"
                            onClick={handleCorpusSync}
                            disabled={syncing || mountsUnavailable}
                        >
                            {syncing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                            <span>Sync corpus now</span>
                        </button>
                        <button className="btn btn-secondary" onClick={() => navigate('/upload')}>
                            <UploadCloud size={15} />
                            <span>Upload PDF + JSON</span>
                        </button>
                    </EmptyState>
                ) : filteredDocuments.length === 0 ? (
                    <EmptyState
                        icon={<Search size={36} />}
                        title="No matching documents"
                        message="Try another title or clear a facet filter."
                    >
                        <button type="button" className="btn btn-sm btn-secondary" onClick={clearFilters}>
                            Clear filters
                        </button>
                    </EmptyState>
                ) : (
                    <div className="family-groups">
                        {familyGroups.map((group) => {
                            const collapsed = collapsedFamilies.has(group.familyKey);
                            const groupReviewed = group.editions.reduce((sum, d) => sum + (d.stats?.reviewed || 0), 0);
                            const groupSections = group.editions.reduce((sum, d) => sum + (d.total_sections || 0), 0);
                            const groupPct = groupSections ? Math.round((groupReviewed / groupSections) * 100) : 0;
                            return (
                                <section key={group.familyKey} className="family-group">
                                    <header className="family-group-header">
                                        <button
                                            type="button"
                                            className="family-group-toggle"
                                            onClick={() => toggleFamily(group.familyKey)}
                                            aria-expanded={!collapsed}
                                        >
                                            <ChevronDown
                                                size={15}
                                                className={`family-group-chevron ${collapsed ? 'collapsed' : ''}`}
                                                aria-hidden="true"
                                            />
                                            <h3>{group.title}</h3>
                                        </button>
                                        <p>
                                            {group.editions.length} edition{group.editions.length === 1 ? '' : 's'}
                                            {group.latestYear ? ` · latest ${group.latestYear}` : ''}
                                        </p>
                                        <div className="family-group-side">
                                            {group.outsideGate && (
                                                <span className="chip chip-danger">
                                                    <AlertTriangle size={12} aria-hidden="true" />
                                                    Outside gate
                                                </span>
                                            )}
                                            <span
                                                className="family-group-progress"
                                                title={`${groupReviewed.toLocaleString()} of ${groupSections.toLocaleString()} sections reviewed`}
                                            >
                                                <span className="progress-bar">
                                                    <span
                                                        className={`progress-bar-fill ${groupPct === 100 ? 'is-complete' : ''}`}
                                                        style={{ width: `${groupPct}%` }}
                                                    />
                                                </span>
                                                {groupPct}%
                                            </span>
                                        </div>
                                    </header>
                                    {!collapsed && renderDocuments(group.editions)}
                                </section>
                            );
                        })}
                    </div>
                )}
            </div>
        </AppShell>
    );
};

export default DashboardPage;
