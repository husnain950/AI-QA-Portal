import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    AlertTriangle, ChevronDown, Clock, Database, FileText, Loader2, RefreshCw,
    Search, Star, UploadCloud,
} from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import EmptyState from '../components/ui/EmptyState';
import ProgressBar from '../components/ui/ProgressBar';
import Skeleton from '../components/ui/Skeleton';
import LibraryToolbar from '../components/library/LibraryToolbar';
import FilterPanel from '../components/library/FilterPanel';
import SelectionBar from '../components/library/SelectionBar';
import { DocumentCard, DocumentCompactRow, DocumentRow } from '../components/library/DocumentItem';
import { useDocumentStore } from '../stores/documentStore';
import { useLibraryStore } from '../stores/libraryStore';
import { useUiStore } from '../stores/uiStore';
import { useFavorites } from '../utils/favorites';
import { useRecents } from '../utils/recents';
import { api, corpusApi } from '../utils/api';
import { queryClient } from '../queryClient';
import {
    DEFAULT_SORT,
    SORT_VALUES,
    groupDocumentsByFamily,
    buildApiParams,
    countActiveFilters,
} from '../utils/libraryQuery';
import {
    EMPTY_FACETS,
    clearChip,
    hasActiveFilters,
    libraryFilterChips,
    parseLibrarySearchParams,
    serializeLibrarySearchParams,
} from '../utils/libraryState';
import { exportDocumentsCsv } from '../utils/csvExport';
import { CORPUS_MOUNT_HINT, describeCorpusSync } from '../utils/corpusStatus';
import { isTypingTarget } from '../utils/keyboard';
import { timeAgo } from '../utils/time';

const VIEW_KEY = 'qa-portal-library-view';
const SORT_KEY = 'qa-portal-library-sort';
const SEARCH_DEBOUNCE_MS = 250;
const LAYOUTS = new Set(['list', 'cards', 'compact']);

function readPref(key, valid, fallback) {
    try {
        const value = window.localStorage?.getItem(key);
        return valid.has(value) ? value : fallback;
    } catch {
        return fallback;
    }
}

function readSortPref() {
    return readPref(SORT_KEY, SORT_VALUES, '');
}

function writePref(key, value) {
    try {
        window.localStorage?.setItem(key, value);
    } catch {
        // localStorage unavailable
    }
}

const DashboardPage = () => {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const deleteDocument = useDocumentStore((state) => state.deleteDocument);
    const pushToast = useUiStore((state) => state.pushToast);
    const confirmDialog = useUiStore((state) => state.confirmDialog);

    const parsed = useMemo(() => parseLibrarySearchParams(searchParams), [searchParams]);
    const sort = parsed.sort || readSortPref() || DEFAULT_SORT;
    const { view, group, facets } = parsed;
    const state = useMemo(
        () => ({ query: parsed.query, sort, view, group, facets }),
        [parsed.query, sort, view, group, facets],
    );

    const [queryInput, setQueryInput] = useState(parsed.query);
    const [layout, setLayout] = useState(() => readPref(VIEW_KEY, LAYOUTS, 'list'));
    const [corpusStatus, setCorpusStatus] = useState(null);
    const [syncing, setSyncing] = useState(false);
    const [panelOpen, setPanelOpen] = useState(false);
    const [collapsedFamilies, setCollapsedFamilies] = useState(() => new Set());
    const [selection, setSelection] = useState(() => new Set());
    const [activeIndex, setActiveIndex] = useState(-1);

    const favoriteIds = useFavorites((state) => state.ids);
    const toggleFavorite = useFavorites((state) => state.toggle);
    const addFavorites = useFavorites((state) => state.addMany);
    const recentIds = useRecents((state) => state.ids);

    const items = useLibraryStore((state) => state.items);
    const total = useLibraryStore((state) => state.total);
    const nextCursor = useLibraryStore((state) => state.nextCursor);
    const facetPayload = useLibraryStore((state) => state.facets);
    const library = useLibraryStore((state) => state.library);
    const status = useLibraryStore((state) => state.status);
    const storeError = useLibraryStore((state) => state.error);
    const loadingMore = useLibraryStore((state) => state.loadingMore);
    const storeKey = useLibraryStore((state) => state.key);
    const load = useLibraryStore((state) => state.load);
    const loadMore = useLibraryStore((state) => state.loadMore);
    const reload = useLibraryStore((state) => state.reload);

    const syncMeta = corpusStatus ? describeCorpusSync(corpusStatus) : null;
    const mountsUnavailable = Boolean(syncMeta && !syncMeta.canSync);
    const searching = Boolean(parsed.query.trim());

    // --- URL state -----------------------------------------------------------

    const commit = useCallback((next) => {
        const serialized = serializeLibrarySearchParams(next);
        if (serialized.toString() !== searchParams.toString()) {
            setSearchParams(serialized, { replace: true });
        }
    }, [searchParams, setSearchParams]);

    const commitRef = useRef(commit);
    commitRef.current = commit;
    const stateRef = useRef(state);
    stateRef.current = state;

    // Debounced search commits to the URL; the URL drives the query.
    useEffect(() => {
        const timer = window.setTimeout(() => {
            if (queryInput !== stateRef.current.query) {
                commitRef.current({ ...stateRef.current, query: queryInput });
            }
        }, SEARCH_DEBOUNCE_MS);
        return () => window.clearTimeout(timer);
    }, [queryInput]);

    // External navigation (back/forward, saved view, chip removal) syncs the box.
    useEffect(() => {
        setQueryInput((current) => (current === parsed.query ? current : parsed.query));
    }, [parsed.query]);

    const commitFacets = useCallback((nextFacets) => {
        commitRef.current({ ...stateRef.current, facets: nextFacets });
    }, []);

    const setSort = (value) => {
        writePref(SORT_KEY, value);
        commit({ ...state, sort: value });
    };

    const setView = (value) => commit({ ...state, view: value });
    const setGroup = (value) => commit({ ...state, group: value });
    const setLayoutPersisted = (value) => {
        setLayout(value);
        writePref(VIEW_KEY, value);
    };

    const clearFilters = () => {
        setQueryInput('');
        commit({ query: '', sort, view: 'all', group, facets: { ...EMPTY_FACETS } });
    };

    const removeChip = (key) => {
        const next = clearChip(state, key);
        if (next.query !== state.query) setQueryInput(next.query);
        commit(next);
    };

    const applySavedView = (search) => {
        setSearchParams(new URLSearchParams(search), { replace: false });
    };

    // --- Server-driven list --------------------------------------------------

    const idsKey = view === 'favorites'
        ? favoriteIds.join(',')
        : view === 'recent' ? recentIds.join(',') : '';
    const stateKey = `${serializeLibrarySearchParams(state)}::${idsKey}`;
    const apiParams = useMemo(
        () => buildApiParams(state, { favoriteIds, recentIds }),
        [state, favoriteIds, recentIds],
    );

    useEffect(() => {
        if (storeKey !== stateKey) load(stateKey, apiParams);
    }, [stateKey, storeKey, load, apiParams]);

    // A favorite toggled off inside the Favorites view should disappear.
    const displayItems = useMemo(() => {
        if (view === 'favorites') {
            const favorites = new Set(favoriteIds);
            return items.filter((doc) => favorites.has(doc.id));
        }
        if (view === 'recent') {
            const order = new Map(recentIds.map((id, index) => [id, index]));
            return [...items].sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
        }
        return items;
    }, [items, view, favoriteIds, recentIds]);

    const familyGroups = useMemo(
        () => (group ? groupDocumentsByFamily(displayItems, sort) : null),
        [group, displayItems, sort],
    );

    // Infinite scroll: sentinel observed with a generous lead, plus a manual button.
    const sentinelRef = useRef(null);
    useEffect(() => {
        const el = sentinelRef.current;
        if (!el || !nextCursor || typeof IntersectionObserver === 'undefined') return undefined;
        const observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) loadMore();
        }, { rootMargin: '800px' });
        observer.observe(el);
        return () => observer.disconnect();
    }, [nextCursor, loadMore]);

    // --- Corpus sync ---------------------------------------------------------

    const refreshCorpusStatus = useCallback(async () => {
        try {
            setCorpusStatus(await corpusApi.status());
        } catch {
            setCorpusStatus(null);
        }
    }, []);

    useEffect(() => {
        refreshCorpusStatus();
    }, [refreshCorpusStatus]);

    const handleCorpusSync = async () => {
        try {
            setSyncing(true);
            // An idempotency key, because the only thing stopping a second
            // concurrent sync was local React state: `sync_running` is fetched once
            // on mount and never re-polled, so a sync started in another tab left
            // this button enabled. `TriagePage` already passes one for its job.
            const summary = await corpusApi.sync(
                { metrics: true },
                { idempotencyKey: `corpus-sync-${Date.now()}` },
            );
            // Every corpus the server reports, read off the summary itself. This
            // named `ordinance` and `acts` and nothing else, so the Rules corpus --
            // which has existed since #19 -- was silently dropped from the message.
            // `corpus_sync.run_corpus_sync` gives EVERY registered corpus a key for
            // exactly this reason ("so a reader of the summary can tell 'synced
            // nothing' from 'was not asked to'"); reading them means a fourth corpus
            // needs no change here.
            const counts = Object.entries(summary)
                .filter(([, part]) => part && typeof part === 'object' && 'imported' in part)
                .map(([label, part]) => `${part.skipped_corpus
                    ? `${label} not mounted`
                    : `${label} ${part.imported ?? 0} imported / ${part.skipped ?? 0} skipped`}`)
                .join('; ');
            const withdrawn = summary.withdrawn
                ? ` ${summary.withdrawn} withdrawn.` : '';
            pushToast({
                type: 'success',
                message: `Corpus sync finished — ${counts || 'nothing to sync'}.${withdrawn}`,
            });
            await reload();
            await refreshCorpusStatus();
        } catch (err) {
            pushToast({ type: 'error', message: 'Corpus sync failed: ' + (err.message || 'Unknown error') });
        } finally {
            setSyncing(false);
            // Whatever happened, re-read whether a sync is still running: this
            // component's `syncing` flag is local, the server's `sync_running` is
            // the truth, and a reload mid-sync loses the local one entirely.
            await refreshCorpusStatus();
        }
    };

    // --- Document actions ----------------------------------------------------

    const handleOpen = useCallback((docId) => {
        navigate(`/review/${docId}`);
    }, [navigate]);

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
            reload();
        } catch (err) {
            pushToast({ type: 'error', message: 'Failed to delete document: ' + err.message });
        }
    };

    const handleExport = (docId, format) => {
        window.open(api.getDownloadUrl(`/documents/${docId}/export?format=${format}`));
    };

    const handleNewVersion = useCallback(async () => {
        pushToast({ type: 'success', message: 'New JSON version is active. Open the document to see what changed.' });
        reload();
    }, [pushToast, reload]);

    // --- Bulk selection ------------------------------------------------------

    const toggleSelect = useCallback((docId) => {
        setSelection((prev) => {
            const next = new Set(prev);
            if (next.has(docId)) next.delete(docId);
            else next.add(docId);
            return next;
        });
    }, []);

    const selectedDocs = useMemo(
        () => displayItems.filter((doc) => selection.has(doc.id)),
        [displayItems, selection],
    );

    const bulkDelete = async () => {
        const docs = selectedDocs;
        if (!docs.length) return;
        const ok = await confirmDialog({
            title: `Delete ${docs.length} document${docs.length === 1 ? '' : 's'}?`,
            message: 'This removes annotations, footnotes validation, and source files for every selected document.',
            confirmLabel: `Delete ${docs.length}`,
        });
        if (!ok) return;
        const results = await Promise.allSettled(docs.map((doc) => api.delete(`/documents/${doc.id}`)));
        const failed = results.filter((result) => result.status === 'rejected').length;
        await queryClient.invalidateQueries({ queryKey: ['documents'] });
        setSelection(new Set());
        reload();
        pushToast(
            failed
                ? { type: 'error', message: `Deleted ${docs.length - failed} of ${docs.length}; ${failed} failed` }
                : { type: 'success', message: `Deleted ${docs.length} document${docs.length === 1 ? '' : 's'}` },
        );
    };

    // --- Keyboard navigation ---------------------------------------------------

    useEffect(() => {
        const onKey = (event) => {
            if (event.key === '/') {
                if (isTypingTarget(event)) return;
                event.preventDefault();
                document.getElementById('document-filter')?.focus();
                return;
            }
            if (isTypingTarget(event)) return;
            if (event.key === 'Escape') {
                if (selection.size) setSelection(new Set());
                setActiveIndex(-1);
                return;
            }
            if (!displayItems.length) return;
            if (event.key === 'j' || event.key === 'k') {
                event.preventDefault();
                const delta = event.key === 'j' ? 1 : -1;
                setActiveIndex((current) => Math.min(
                    displayItems.length - 1,
                    Math.max(0, (current < 0 ? (delta > 0 ? -1 : displayItems.length) : current) + delta),
                ));
            } else if (event.key === 'Enter' && activeIndex >= 0) {
                event.preventDefault();
                handleOpen(displayItems[activeIndex].id);
            } else if (event.key === 'x' && activeIndex >= 0) {
                event.preventDefault();
                toggleSelect(displayItems[activeIndex].id);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [displayItems, activeIndex, selection.size, handleOpen, toggleSelect]);

    useEffect(() => {
        if (activeIndex < 0 || !displayItems[activeIndex]) return;
        const id = displayItems[activeIndex].id;
        const escaped = window.CSS?.escape ? window.CSS.escape(id) : id;
        document.querySelector(`[data-doc-id="${escaped}"]`)
            ?.scrollIntoView?.({ block: 'nearest' });
    }, [activeIndex, displayItems]);

    // --- Derived view data -----------------------------------------------------

    const chips = useMemo(() => libraryFilterChips(state), [state]);
    const filterCount = useMemo(() => countActiveFilters(facets), [facets]);
    const filtersActive = hasActiveFilters(state);
    const libraryTotal = library?.documents ?? facetPayload?.library_total ?? total;
    const loading = status === 'loading';
    const toggleFamily = (familyKey) => {
        setCollapsedFamilies((prev) => {
            const next = new Set(prev);
            if (next.has(familyKey)) next.delete(familyKey);
            else next.add(familyKey);
            return next;
        });
    };

    const ItemComponent = layout === 'cards'
        ? DocumentCard
        : layout === 'compact' ? DocumentCompactRow : DocumentRow;

    const renderItem = (doc) => (
        <ItemComponent
            key={doc.id}
            doc={doc}
            selected={selection.has(doc.id)}
            onToggleSelect={toggleSelect}
            isFavorite={favoriteIds.includes(doc.id)}
            onToggleFavorite={toggleFavorite}
            onOpen={() => handleOpen(doc.id)}
            onDelete={handleDelete}
            onExport={handleExport}
            onNewVersion={handleNewVersion}
            keyboardActive={displayItems[activeIndex]?.id === doc.id}
        />
    );

    const renderList = (docs) => {
        if (layout === 'cards') {
            return <div className="document-grid">{docs.map(renderItem)}</div>;
        }
        if (layout === 'compact') {
            return <div className="doc-compact-list">{docs.map(renderItem)}</div>;
        }
        return <div className="doc-rows">{docs.map(renderItem)}</div>;
    };

    const renderSkeletons = (count) => (
        <div className={layout === 'cards' ? 'document-grid' : 'doc-rows'} aria-label="Loading documents">
            {[...Array(count)].map((_, index) => (
                <div key={index} className="doc-row doc-row-skeleton">
                    <div className="doc-row-main">
                        <Skeleton width={`${50 - (index % 3) * 8}%`} height={15} />
                        <Skeleton width={`${34 - (index % 2) * 6}%`} height={11} />
                    </div>
                    <Skeleton width={120} height={10} />
                    <Skeleton width={90} height={26} />
                </div>
            ))}
        </div>
    );

    const renderBody = () => {
        if (loading) return renderSkeletons(6);
        if (status === 'error') {
            return (
                <EmptyState
                    icon={<AlertTriangle size={44} />}
                    title="Couldn't load the library"
                    message={`The API didn't respond (${storeError}). This is a load failure, not an empty library — the documents are still there.`}
                >
                    <button className="btn btn-primary" onClick={reload}>
                        <RefreshCw size={15} />
                        <span>Retry</span>
                    </button>
                </EmptyState>
            );
        }
        if (!libraryTotal && !filtersActive) {
            return (
                <EmptyState
                    icon={<FileText size={44} />}
                    title="Corpus is empty"
                    message={mountsUnavailable
                        ? 'This host has no Ordinance/Acts pipeline mounts. From a machine that already has the corpus, run make push-remote BASE_URL=<this portal>, or upload a PDF + JSON pair below.'
                        : 'Seed from the configured Ordinance + Acts pipeline output, then review side-by-side. Closed loop: convert → sync → review → export QA → import findings.'}
                >
                    <button
                        className="btn btn-primary"
                        onClick={handleCorpusSync}
                        disabled={syncing || mountsUnavailable}
                        title={mountsUnavailable
                            ? 'Pipeline mounts are not on this host — use make push-remote or Upload'
                            : undefined}
                    >
                        {syncing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                        <span>Sync corpus now</span>
                    </button>
                    <button className="btn btn-secondary" onClick={() => navigate('/upload')}>
                        <UploadCloud size={15} />
                        <span>Upload PDF + JSON</span>
                    </button>
                </EmptyState>
            );
        }
        if (view === 'favorites' && !favoriteIds.length) {
            return (
                <EmptyState
                    icon={<Star size={40} />}
                    title="No favorites yet"
                    message="Star any document to pin it here. Favorites are stored on this browser."
                >
                    <button className="btn btn-secondary" onClick={() => setView('all')}>
                        Browse all documents
                    </button>
                </EmptyState>
            );
        }
        if (view === 'recent' && !recentIds.length) {
            return (
                <EmptyState
                    icon={<Clock size={40} />}
                    title="Nothing opened yet"
                    message="Documents you open for review land here, newest first."
                >
                    <button className="btn btn-secondary" onClick={() => setView('all')}>
                        Browse all documents
                    </button>
                </EmptyState>
            );
        }
        if (total === 0) {
            return (
                <EmptyState
                    icon={<Search size={36} />}
                    title={searching ? `No documents match “${parsed.query}”` : 'No documents match these filters'}
                    message={searching
                        ? 'Search covers document titles and source filenames. Try a shorter term, or clear a filter.'
                        : 'The active filters exclude everything. Loosen one, or clear them all.'}
                >
                    {searching && (
                        <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                                setQueryInput('');
                                commit({ ...state, query: '' });
                            }}
                        >
                            Clear search
                        </button>
                    )}
                    <button type="button" className="btn btn-sm btn-secondary" onClick={clearFilters}>
                        Clear all filters
                    </button>
                </EmptyState>
            );
        }
        if (!familyGroups) {
            return renderList(displayItems);
        }
        return (
            <div className="family-groups">
                {familyGroups.map((familyGroup) => {
                    const collapsed = collapsedFamilies.has(familyGroup.familyKey);
                    const groupReviewed = familyGroup.editions.reduce((sum, doc) => sum + (doc.stats?.reviewed || 0), 0);
                    const groupSections = familyGroup.editions.reduce((sum, doc) => sum + (doc.total_sections || 0), 0);
                    const groupPct = groupSections ? Math.round((groupReviewed / groupSections) * 100) : 0;
                    return (
                        <section key={familyGroup.familyKey} className="family-group">
                            <header className="family-group-header">
                                <button
                                    type="button"
                                    className="family-group-toggle"
                                    onClick={() => toggleFamily(familyGroup.familyKey)}
                                    aria-expanded={!collapsed}
                                >
                                    <ChevronDown
                                        size={15}
                                        className={`family-group-chevron ${collapsed ? 'collapsed' : ''}`}
                                        aria-hidden="true"
                                    />
                                    <h3>{familyGroup.title}</h3>
                                </button>
                                <p>
                                    {familyGroup.editions.length} edition{familyGroup.editions.length === 1 ? '' : 's'}
                                    {familyGroup.latestYear ? ` · latest ${familyGroup.latestYear}` : ''}
                                    {nextCursor ? ' · loaded so far' : ''}
                                </p>
                                <div className="family-group-side">
                                    {familyGroup.outsideGate && (
                                        <span className="chip chip-danger">
                                            <AlertTriangle size={12} aria-hidden="true" />
                                            Outside gate
                                        </span>
                                    )}
                                    <span
                                        className="family-group-progress"
                                        title={`${groupReviewed.toLocaleString()} of ${groupSections.toLocaleString()} sections reviewed`}
                                    >
                                        <ProgressBar pct={groupPct} />
                                        {groupPct}%
                                    </span>
                                </div>
                            </header>
                            {!collapsed && renderList(familyGroup.editions)}
                        </section>
                    );
                })}
            </div>
        );
    };

    return (
        <AppShell title="Library" scrollable>
            <div className="dashboard-container">
                <header className="library-header">
                    <div className="library-header-text">
                        <h1>Library</h1>
                        <p className="library-stats">
                            <button
                                type="button"
                                className="library-stat library-stat-btn"
                                onClick={clearFilters}
                                title="Show all documents"
                            >
                                <strong>{(library?.documents ?? 0).toLocaleString()}</strong> documents
                            </button>
                            <button
                                type="button"
                                className={`library-stat library-stat-btn is-warning ${facets.flagged ? 'active' : ''}`}
                                onClick={() => commitFacets({ ...facets, flagged: !facets.flagged })}
                                aria-pressed={facets.flagged}
                                title="Show only documents with flagged sections"
                            >
                                <strong>{(library?.flagged ?? 0).toLocaleString()}</strong> flagged
                            </button>
                            <button
                                type="button"
                                className={`library-stat library-stat-btn is-success ${facets.review.includes('complete') ? 'active' : ''}`}
                                onClick={() => commitFacets({
                                    ...facets,
                                    review: facets.review.includes('complete')
                                        ? facets.review.filter((value) => value !== 'complete')
                                        : [...facets.review, 'complete'],
                                })}
                                aria-pressed={facets.review.includes('complete')}
                                title="Show fully reviewed documents"
                            >
                                <strong>{(library?.complete ?? 0).toLocaleString()}</strong> complete
                            </button>
                        </p>
                        <p className="library-sync-line">
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

                <LibraryToolbar
                    queryInput={queryInput}
                    onQueryInput={setQueryInput}
                    searching={searching}
                    sort={sort}
                    onSort={setSort}
                    view={view}
                    onView={setView}
                    viewCounts={{ favorites: favoriteIds.length, recent: recentIds.length }}
                    layout={layout}
                    onLayout={setLayoutPersisted}
                    group={group}
                    onToggleGroup={() => setGroup(!group)}
                    filterCount={filterCount}
                    onOpenFilters={() => setPanelOpen(true)}
                    chips={chips}
                    onRemoveChip={removeChip}
                    onClearAll={clearFilters}
                    total={total}
                    libraryTotal={libraryTotal}
                    loading={loading}
                    currentSearch={searchParams.toString()}
                    onApplySavedView={applySavedView}
                />

                {renderBody()}

                {status === 'ready' && displayItems.length > 0 && (
                    <div className="library-footer">
                        <span className="library-footer-count">
                            Showing {displayItems.length.toLocaleString()} of {total.toLocaleString()}
                            {familyGroups ? ` · ${familyGroups.length} famil${familyGroups.length === 1 ? 'y' : 'ies'}` : ''}
                        </span>
                        {nextCursor && (
                            <button
                                type="button"
                                className="btn btn-sm btn-secondary"
                                onClick={loadMore}
                                disabled={loadingMore}
                            >
                                {loadingMore ? <Loader2 size={14} className="animate-spin" /> : null}
                                <span>Load more</span>
                            </button>
                        )}
                        <div ref={sentinelRef} className="library-sentinel" aria-hidden="true" />
                    </div>
                )}
                {loadingMore && renderSkeletons(2)}

                <FilterPanel
                    open={panelOpen}
                    onClose={() => setPanelOpen(false)}
                    facets={facets}
                    facetCounts={facetPayload}
                    onChangeFacets={commitFacets}
                    onClearAll={() => {
                        clearFilters();
                    }}
                    filteredTotal={facetPayload?.totals?.documents ?? total}
                />

                <SelectionBar
                    count={selection.size}
                    loadedCount={displayItems.length}
                    onSelectAllLoaded={() => setSelection(new Set(displayItems.map((doc) => doc.id)))}
                    onFavorite={() => {
                        addFavorites([...selection]);
                        pushToast({ type: 'success', message: `Added ${selection.size} to favorites` });
                    }}
                    onExportCsv={() => exportDocumentsCsv(selectedDocs)}
                    onDelete={bulkDelete}
                    onClear={() => setSelection(new Set())}
                />
            </div>
        </AppShell>
    );
};

export default DashboardPage;
