import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    ChevronDown, ChevronRight, ExternalLink, GitBranch, Inbox, FileOutput,
    RotateCcw, X, Search,
} from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import EmptyState from '../components/ui/EmptyState';
import ProgressBar from '../components/ui/ProgressBar';
import Skeleton from '../components/ui/Skeleton';
import StatusChip from '../components/ui/StatusChip';
import { TRIAGE_TONES } from '../components/ui/statusTones';
import DropdownMenu from '../components/ui/DropdownMenu';
import { api, jobsApi } from '../utils/api';
import { formatSectionLabel } from '../utils/tocLabels';
import { editionDateFromName } from '../utils/editions';
import { timelinePath } from '../utils/timeline';
import { useUiStore } from '../stores/uiStore';
import { isTypingTarget } from '../utils/keyboard';

const TRIAGE_FILTERS = [
    { id: 'new', label: 'New' },
    { id: 'parse_bug', label: 'Parse bug' },
    { id: 'source_defect', label: 'Source defect' },
    { id: 'deliberate', label: 'Deliberate' },
    { id: 'not_a_defect', label: 'Not a defect' },
    { id: 'fixed', label: 'Fixed' },
];

const BULK_ACTIONS = [
    { triage: 'parse_bug', label: 'Parse bug' },
    { triage: 'not_a_defect', label: 'Not a defect' },
    { triage: 'deliberate', label: 'Deliberate' },
    { triage: 'source_defect', label: 'Source defect' },
    { triage: 'fixed', label: 'Fixed' },
];

const SORTS = [
    { id: 'score', label: 'Sort: Score' },
    { id: 'blast', label: 'Sort: Blast radius' },
    { id: 'page', label: 'Sort: Page' },
];

function groupBy(items, keyFn) {
    const map = new Map();
    for (const item of items) {
        const key = keyFn(item);
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(item);
    }
    return map;
}

function sortRows(rows, sort) {
    const bySort = {
        score: (a, b) => (b.score || 0) - (a.score || 0),
        blast: (a, b) => (b.blast_radius || 1) - (a.blast_radius || 1)
            || (b.score || 0) - (a.score || 0),
        page: (a, b) => (a.start_page ?? Infinity) - (b.start_page ?? Infinity),
    };
    return [...rows].sort(bySort[sort] || bySort.score);
}

export default function TriagePage() {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const pushToast = useUiStore((s) => s.pushToast);
    const promptDialog = useUiStore((s) => s.promptDialog);
    const reviewerName = useUiStore((s) => s.reviewerName);

    const [findings, setFindings] = useState([]);
    const [stats, setStats] = useState({ total: 0, done: 0, left: 0, by_triage: {} });
    const [cursor, setCursor] = useState(0);
    const [skipped, setSkipped] = useState(() => new Set());
    const [selected, setSelected] = useState(() => new Set());
    const [expanded, setExpanded] = useState(() => new Set());
    const [textFilter, setTextFilter] = useState('');
    const undoRef = useRef(null);
    const lastApproveRef = useRef(0);
    const lastSelectedRef = useRef(null);
    const rowRefs = useRef([]);

    const triageFilter = searchParams.get('triage') || 'new';
    const detectorFilter = searchParams.get('detector') || '';
    const sort = searchParams.get('sort') || 'score';

    const findingsQuery = useInfiniteQuery({
        queryKey: ['findings-v2', triageFilter, detectorFilter, sort, textFilter.trim()],
        initialPageParam: null,
        queryFn: async ({ pageParam, signal }) => {
            const qs = new URLSearchParams();
            if (triageFilter) qs.set('triage', triageFilter);
            if (detectorFilter) qs.set('detector', detectorFilter);
            if (textFilter.trim()) qs.set('q', textFilter.trim());
            qs.set('sort', sort);
            qs.set('limit', '200');
            if (pageParam) qs.set('cursor', pageParam);
            return api.get(`/v2/findings?${qs.toString()}`, { signal });
        },
        getNextPageParam: (page) => page.next_cursor || undefined,
        placeholderData: (previous) => previous,
    });

    const queryData = findingsQuery.data;
    const refetchFindings = findingsQuery.refetch;
    const load = useCallback(async () => {
        await refetchFindings();
    }, [refetchFindings]);

    useEffect(() => {
        if (!queryData) return;
        const rows = queryData.pages.flatMap((page) => page.items || []);
        setFindings(rows);
        setStats(queryData.pages[0]?.stats || {
            total: queryData.pages[0]?.total || rows.length,
            done: 0,
            left: rows.length,
            by_triage: {},
        });
        setSelected(new Set());
    }, [queryData]);

    useEffect(() => {
        if (findingsQuery.error) {
            pushToast({
                type: 'error',
                message: findingsQuery.error.message || 'Failed to load findings',
            });
        }
    }, [findingsQuery.error, pushToast]);

    const openFinding = useCallback(async (finding) => {
        if (!reviewerName?.trim()) {
            pushToast({ type: 'error', message: 'Set a reviewer name before starting a review session' });
            return;
        }
        let clientSessionId = sessionStorage.getItem('crx-review-client-session');
        if (!clientSessionId) {
            clientSessionId = crypto.randomUUID();
            sessionStorage.setItem('crx-review-client-session', clientSessionId);
        }
        try {
            const session = await api.post('/v2/review-sessions', {
                client_session_id: clientSessionId,
                finding_id: finding.id,
                filters: {
                    detector: detectorFilter || undefined,
                    severity: finding.severity || undefined,
                },
                sort: 'risk_desc',
            });
            await api.post(`/v2/review-assignments/${finding.id}`, {
                client_session_id: clientSessionId,
            });
            const query = new URLSearchParams({
                session: session.id,
                finding: String(finding.id),
            });
            navigate(`/review/${finding.document_id}/${finding.section_id}?${query}`);
        } catch (err) {
            pushToast({ type: 'error', message: err.message || 'Could not start review session' });
        }
    }, [detectorFilter, navigate, pushToast, reviewerName]);

    const detectorOptions = useMemo(() => {
        const set = new Set(findings.map((f) => f.detector).filter(Boolean));
        if (detectorFilter) set.add(detectorFilter);
        return [...set].sort();
    }, [findings, detectorFilter]);

    const visible = useMemo(() => {
        const q = textFilter.trim().toLowerCase();
        return findings.filter((f) => {
            if (skipped.has(f.id)) return false;
            if (!q) return true;
            return [
                f.detector,
                f.document_name,
                f.family_label,
                f.section_code,
                f.section_heading,
                f.summary,
            ]
                .filter(Boolean)
                .join(' ')
                .toLowerCase()
                .includes(q);
        });
    }, [findings, skipped, textFilter]);

    const grouped = useMemo(() => {
        const map = groupBy(visible, (f) => f.detector || 'unknown');
        const entries = [...map.entries()].map(([detector, rows]) => [detector, sortRows(rows, sort)]);
        entries.sort((a, b) => b[1].length - a[1].length);
        return entries;
    }, [visible, sort]);

    const flat = useMemo(() => grouped.flatMap(([, rows]) => rows), [grouped]);
    const maxScore = useMemo(
        () => flat.reduce((m, f) => Math.max(m, f.score || 0), 0) || 1,
        [flat],
    );

    useEffect(() => {
        if (cursor >= flat.length) setCursor(Math.max(0, flat.length - 1));
    }, [flat.length, cursor]);

    const setTriage = useCallback(async (finding, triage, note = '') => {
        const prev = { ...finding };
        setFindings((rows) => rows.map((r) => (r.id === finding.id ? { ...r, triage } : r)));
        try {
            await api.patch(`/findings/${finding.id}/status`, { triage, note });
            undoRef.current = async () => {
                try {
                    await api.patch(`/findings/${finding.id}/status`, {
                        triage: prev.triage,
                        note: prev.triage_note || '',
                    });
                    await load();
                    pushToast({ type: 'info', message: 'Finding restored' });
                } catch (err) {
                    pushToast({ type: 'error', message: err.message || 'Undo failed' });
                }
            };
            pushToast({
                type: 'success',
                message: `Marked ${finding.detector} as ${triage.replace(/_/g, ' ')}`,
                onUndo: () => undoRef.current?.(),
            });
            setCursor((c) => Math.min(c + 1, Math.max(0, flat.length - 1)));
        } catch (err) {
            setFindings((rows) => rows.map((r) => (r.id === finding.id ? prev : r)));
            pushToast({ type: 'error', message: err.message });
        }
    }, [flat.length, load, pushToast]);

    const bulkSetTriage = useCallback(async (triage) => {
        const targets = flat.filter((f) => selected.has(f.id));
        if (!targets.length) return;
        const previous = targets.map((f) => ({ id: f.id, triage: f.triage, note: f.triage_note || '' }));
        const ids = new Set(targets.map((f) => f.id));
        setFindings((rows) => rows.map((r) => (ids.has(r.id) ? { ...r, triage } : r)));
        setSelected(new Set());
        const idempotencyKey = crypto.randomUUID();
        try {
            await api.post('/v2/findings/bulk-triage', {
                items: targets.map((f) => ({
                    id: f.id,
                    triage,
                    expected_prior: f.triage,
                    note: '',
                })),
            }, false, { headers: { 'Idempotency-Key': idempotencyKey } });
        } catch (err) {
            setFindings((rows) => rows.map((row) => previous.find((p) => p.id === row.id)
                ? { ...row, triage: previous.find((p) => p.id === row.id).triage }
                : row));
            pushToast({ type: 'error', message: err.message || 'Atomic bulk action failed' });
            await load();
            return;
        }
        undoRef.current = async () => {
            try {
                await api.post('/v2/findings/bulk-triage', {
                    items: previous.map((p) => ({
                        id: p.id,
                        triage: p.triage,
                        expected_prior: triage,
                        note: p.note,
                    })),
                }, false, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
                pushToast({ type: 'info', message: `Restored ${previous.length} finding${previous.length === 1 ? '' : 's'}` });
            } catch (err) {
                pushToast({ type: 'error', message: err.message || 'Atomic undo failed' });
            }
            await load();
        };
        pushToast({
            type: 'success',
            message: `Marked ${targets.length} finding${targets.length === 1 ? '' : 's'} as ${triage.replace(/_/g, ' ')}`,
            onUndo: () => undoRef.current?.(),
        });
        await load();
    }, [flat, selected, load, pushToast]);

    const approveVariants = useCallback(async (finding) => {
        if (!finding.variant_key) {
            pushToast({ type: 'error', message: 'No variant key on this finding' });
            return;
        }
        if (finding.cross_family) {
            const now = Date.now();
            if (now - lastApproveRef.current > 2000) {
                lastApproveRef.current = now;
                pushToast({
                    type: 'info',
                    message: 'Cross-family variant — press a again within 2s to confirm',
                });
                return;
            }
        }
        try {
            const res = await api.post(`/variants/${encodeURIComponent(finding.variant_key)}/approve`, {});
            const n = res.granted || res.count || finding.blast_radius || 1;
            undoRef.current = async () => {
                try {
                    await api.delete(`/variants/${encodeURIComponent(finding.variant_key)}/approve`);
                    await load();
                    pushToast({ type: 'info', message: 'Variant approval undone' });
                } catch (err) {
                    pushToast({ type: 'error', message: err.message || 'Undo failed' });
                }
            };
            pushToast({
                type: 'success',
                message: `Approved ${n} identical leaves`,
                onUndo: () => undoRef.current?.(),
            });
            await setTriage(finding, 'not_a_defect', 'approved via variant');
        } catch (err) {
            pushToast({ type: 'error', message: err.message });
        }
    }, [load, pushToast, setTriage]);

    const exportCase = useCallback(async (finding) => {
        try {
            const result = await jobsApi.run('regression_bundle', {
                finding_id: finding.id,
            }, { idempotencyKey: `regression-${finding.id}-${finding.updated_at || finding.triage}` });
            const anchor = document.createElement('a');
            anchor.href = api.getAssetUrl(result.download_url);
            anchor.download = `finding-${finding.id}-regression.zip`;
            anchor.click();
            pushToast({ type: 'success', message: 'Regression bundle is ready to download' });
        } catch (err) {
            pushToast({ type: 'error', message: err.message || 'Export failed' });
        }
    }, [pushToast]);

    const toggleSelected = useCallback((finding, { range = false } = {}) => {
        const idx = flat.indexOf(finding);
        setSelected((prev) => {
            const next = new Set(prev);
            if (range && lastSelectedRef.current != null) {
                const from = Math.min(lastSelectedRef.current, idx);
                const to = Math.max(lastSelectedRef.current, idx);
                for (let i = from; i <= to; i += 1) next.add(flat[i].id);
            } else if (next.has(finding.id)) {
                next.delete(finding.id);
            } else {
                next.add(finding.id);
            }
            return next;
        });
        lastSelectedRef.current = idx;
    }, [flat]);

    const toggleExpanded = useCallback((id) => {
        setExpanded((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }, []);

    useEffect(() => {
        const onKey = (e) => {
            if (isTypingTarget(e)) return;
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            const f = flat[cursor];
            if (e.key === 'j') {
                e.preventDefault();
                setCursor((c) => Math.min(c + 1, Math.max(0, flat.length - 1)));
            } else if (e.key === 'k') {
                e.preventDefault();
                setCursor((c) => Math.max(0, c - 1));
            } else if (e.key === 'Enter' && f) {
                e.preventDefault();
                openFinding(f);
            } else if (e.key === 'x' && f) {
                e.preventDefault();
                toggleSelected(f);
            } else if (e.key === 'a' && f) {
                e.preventDefault();
                approveVariants(f);
            } else if (e.key === 'f' && f) {
                e.preventDefault();
                promptDialog({
                    title: 'Flag finding',
                    message: 'Disposition note (optional)',
                    defaultValue: '',
                    confirmLabel: 'Mark parse bug',
                }).then((note) => {
                    if (note === null || note === undefined) return;
                    setTriage(f, 'parse_bug', note || '');
                });
            } else if (e.key === 's' && f) {
                e.preventDefault();
                setSkipped((prev) => new Set(prev).add(f.id));
                setCursor((c) => Math.min(c + 1, Math.max(0, flat.length - 1)));
            } else if (e.key === 'u') {
                e.preventDefault();
                undoRef.current?.();
            } else if (e.key === 'Escape' && selected.size) {
                e.preventDefault();
                setSelected(new Set());
            } else if (e.key === '/') {
                e.preventDefault();
                document.getElementById('tq-filter-input')?.focus();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [flat, cursor, openFinding, promptDialog, approveVariants, setTriage, toggleSelected, selected.size]);

    useEffect(() => {
        rowRefs.current[cursor]?.scrollIntoView({ block: 'nearest' });
    }, [cursor]);

    const setParam = (key, value) => {
        const next = new URLSearchParams(searchParams);
        if (!value) next.delete(key);
        else next.set(key, value);
        setSearchParams(next);
    };

    const doneCount = stats.total ? stats.total - (stats.by_triage?.new ?? stats.left ?? 0) : 0;
    const donePct = stats.total ? Math.round((doneCount / stats.total) * 100) : 0;
    const filteredTotal = findingsQuery.data?.pages[0]?.total ?? findings.length;
    const loading = findingsQuery.isPending && findings.length === 0;

    const renderRow = (f) => {
        const idx = flat.indexOf(f);
        const ed = editionDateFromName(f.document_name || '');
        const label = formatSectionLabel(f.section_code, f.section_heading);
        const isExpanded = expanded.has(f.id);
        const isSelected = selected.has(f.id);
        const scorePct = Math.min(100, Math.round(((f.score || 0) / maxScore) * 100));

        return (
            <div key={f.id} className={`tq-row-wrap ${isSelected ? 'selected' : ''}`}>
                <div
                    ref={(el) => {
                        rowRefs.current[idx] = el;
                    }}
                    className={`tq-row ${idx === cursor ? 'active' : ''}`}
                    onClick={(e) => {
                        if (e.shiftKey) {
                            toggleSelected(f, { range: true });
                            return;
                        }
                        setCursor(idx);
                    }}
                >
                    <input
                        type="checkbox"
                        className="tq-row-check"
                        checked={isSelected}
                        aria-label={`Select finding ${label}`}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => toggleSelected(f, { range: e.nativeEvent.shiftKey })}
                    />
                    <button
                        type="button"
                        className="tq-row-expand"
                        aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                        aria-expanded={isExpanded}
                        onClick={(e) => {
                            e.stopPropagation();
                            setCursor(idx);
                            toggleExpanded(f.id);
                        }}
                    >
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    <div className="tq-row-main">
                        <div className="tq-row-title">
                            <span className="tq-row-section">
                                {f.family_label || f.family_key || 'Statute'} · {label}
                            </span>
                            {f.cross_family ? (
                                <StatusChip tone="warning" title="This variant spans multiple statute families">
                                    cross-family
                                </StatusChip>
                            ) : null}
                            {triageFilter !== f.triage && f.triage ? (
                                <StatusChip tone={TRIAGE_TONES[f.triage] || 'neutral'}>
                                    {String(f.triage).replace(/_/g, ' ')}
                                </StatusChip>
                            ) : null}
                        </div>
                        <div className="tq-row-meta">
                            <span>{f.blast_radius || 1} edition{(f.blast_radius || 1) === 1 ? '' : 's'}</span>
                            <span>{ed.label}</span>
                            {f.start_page != null ? <span>p.{f.start_page}</span> : null}
                            {f.summary ? <span className="tq-row-summary" title={f.summary}>{f.summary}</span> : null}
                        </div>
                    </div>
                    <div className="tq-row-side">
                        <div
                            className="tq-score"
                            title={`Priority score ${Math.round(f.score || 0)} (max in view ${Math.round(maxScore)})`}
                        >
                            <span className="tq-score-num">{Math.round(f.score || 0)}</span>
                            <span className="tq-score-bar">
                                <span className="tq-score-fill" style={{ width: `${scorePct}%` }} />
                            </span>
                        </div>
                        <div className="tq-row-actions" onClick={(e) => e.stopPropagation()}>
                            <button
                                type="button"
                                className="btn btn-ghost btn-icon"
                                title="Open in review (Enter)"
                                aria-label="Open in review"
                                onClick={() => openFinding(f)}
                            >
                                <ExternalLink size={14} />
                            </button>
                            <DropdownMenu
                                ariaLabel="Finding actions"
                                items={[
                                    {
                                        key: 'timeline',
                                        label: 'Open section timeline',
                                        icon: GitBranch,
                                        onSelect: () => navigate(timelinePath({
                                            sectionId: f.section_id,
                                            family: f.family_key,
                                            code: f.section_code,
                                        })),
                                    },
                                    {
                                        key: 'export',
                                        label: 'Export regression case',
                                        icon: FileOutput,
                                        onSelect: () => exportCase(f),
                                    },
                                ]}
                            />
                        </div>
                    </div>
                </div>
                {isExpanded ? (
                    <div className="tq-expand">
                        {(f.editions || []).length ? (
                            (f.editions || []).map((edRow) => (
                                <div key={edRow.section_id} className="tq-edition-row">
                                    <span className="tq-edition-name">{edRow.document_name}</span>
                                    <StatusChip
                                        tone={edRow.review_status === 'approved' || edRow.review_status === 'approved_inherited'
                                            ? 'success'
                                            : edRow.review_status === 'has_issues' ? 'danger' : 'neutral'}
                                    >
                                        {String(edRow.review_status || 'pending').replace(/_/g, ' ')}
                                    </StatusChip>
                                    <button
                                        type="button"
                                        className="btn btn-xs btn-secondary"
                                        onClick={() => navigate(`/review/${edRow.document_id}/${edRow.section_id}?from=queue`)}
                                    >
                                        Open
                                    </button>
                                </div>
                            ))
                        ) : (
                            <p className="tq-expand-note">
                                {f.detail?.assertion
                                    || 'Open the leaf to inspect. Approving the variant covers identical output across editions.'}
                            </p>
                        )}
                        {f.variant_key ? (
                            <div className="tq-expand-footer">
                                <span className="tq-variant" title={String(f.variant_key)}>
                                    variant {String(f.variant_key).slice(0, 12)}…
                                </span>
                                <button
                                    type="button"
                                    className="btn btn-xs btn-secondary"
                                    onClick={() => navigate(timelinePath({
                                        sectionId: f.section_id,
                                        family: f.family_key,
                                        code: f.section_code,
                                    }))}
                                >
                                    <GitBranch size={12} />
                                    Timeline
                                </button>
                            </div>
                        ) : null}
                    </div>
                ) : null}
            </div>
        );
    };

    return (
        <AppShell title="Triage" scrollable>
            <div className="tq-page">
                <div className="tq-toolbar">
                    <div className="tq-toolbar-row">
                        <div className="tq-progress" title={`${doneCount} of ${stats.total} findings triaged`}>
                            <span className="tq-progress-text">
                                <strong>{stats.by_triage?.new ?? stats.left ?? visible.length}</strong> open
                                <span className="tq-progress-sep">·</span>
                                {doneCount} of {stats.total} triaged
                            </span>
                            <ProgressBar pct={donePct} ariaHidden />
                        </div>
                        <label className="tq-search" htmlFor="tq-filter-input">
                            <Search size={14} aria-hidden="true" />
                            <span className="sr-only">Filter findings</span>
                            <input
                                id="tq-filter-input"
                                type="search"
                                placeholder="Filter findings…  ( / )"
                                value={textFilter}
                                onChange={(e) => setTextFilter(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Escape') e.currentTarget.blur();
                                }}
                            />
                        </label>
                        <select
                            className="ui-select"
                            value={detectorFilter}
                            onChange={(e) => setParam('detector', e.target.value)}
                            aria-label="Filter by detector"
                        >
                            <option value="">All detectors</option>
                            {detectorOptions.map((d) => (
                                <option key={d} value={d}>{d}</option>
                            ))}
                        </select>
                        <select
                            className="ui-select"
                            value={sort}
                            onChange={(e) => setParam('sort', e.target.value === 'score' ? '' : e.target.value)}
                            aria-label="Sort findings"
                        >
                            {SORTS.map((s) => (
                                <option key={s.id} value={s.id}>{s.label}</option>
                            ))}
                        </select>
                    </div>
                    <div className="tq-filters" role="group" aria-label="Triage state">
                        {TRIAGE_FILTERS.map((f) => {
                            const count = stats.by_triage?.[f.id];
                            return (
                                <button
                                    key={f.id}
                                    type="button"
                                    className={`tq-chip ${triageFilter === f.id ? 'active' : ''}`}
                                    aria-pressed={triageFilter === f.id}
                                    onClick={() => setParam('triage', f.id)}
                                >
                                    {f.label}
                                    {count != null ? <span className="tq-chip-count">{count}</span> : null}
                                </button>
                            );
                        })}
                        {skipped.size > 0 && (
                            <button
                                type="button"
                                className="btn btn-xs btn-ghost tq-skipped-note"
                                onClick={() => setSkipped(new Set())}
                                title="Restore findings skipped this session"
                            >
                                <RotateCcw size={12} />
                                {skipped.size} skipped — restore
                            </button>
                        )}
                    </div>
                </div>

                {selected.size > 0 && (
                    <div className="tq-bulk-bar" role="toolbar" aria-label="Bulk actions">
                        <span className="tq-bulk-count">
                            <strong>{selected.size}</strong> selected
                        </span>
                        <span className="tq-bulk-label">Mark as:</span>
                        {BULK_ACTIONS.filter((a) => a.triage !== triageFilter).map((a) => (
                            <button
                                key={a.triage}
                                type="button"
                                className="btn btn-xs btn-secondary"
                                onClick={() => bulkSetTriage(a.triage)}
                            >
                                {a.label}
                            </button>
                        ))}
                        <button
                            type="button"
                            className="btn btn-xs btn-ghost tq-bulk-clear"
                            onClick={() => setSelected(new Set())}
                            title="Clear selection (Esc)"
                        >
                            <X size={12} />
                            Clear
                        </button>
                    </div>
                )}

                <div className="tq-range" role="status" aria-live="polite">
                    Showing {findings.length ? 1 : 0}–{findings.length} of {filteredTotal}
                    {findingsQuery.data?.pages[0]?.refreshed_at ? (
                        <span title={new Date(findingsQuery.data.pages[0].refreshed_at).toLocaleString()}>
                            refreshed {new Date(findingsQuery.data.pages[0].refreshed_at).toLocaleTimeString()}
                        </span>
                    ) : null}
                </div>

                {loading ? (
                    <div className="tq-skeleton-list" aria-label="Loading findings">
                        {[...Array(6)].map((_, i) => (
                            <div key={i} className="tq-skeleton-row">
                                <Skeleton width={16} height={16} />
                                <div className="tq-skeleton-body">
                                    <Skeleton width={`${55 - (i % 3) * 10}%`} height={13} />
                                    <Skeleton width={`${30 - (i % 2) * 8}%`} height={10} />
                                </div>
                                <Skeleton width={60} height={10} />
                            </div>
                        ))}
                    </div>
                ) : flat.length === 0 ? (
                    <EmptyState
                        icon={<Inbox size={40} />}
                        title={textFilter ? 'No matching findings' : 'No findings in this filter'}
                        message={textFilter
                            ? 'Try a different text filter, or clear it to see everything in this triage state.'
                            : 'Run a corpus sync with detectors enabled, pick another triage state above, or browse the Library.'}
                    >
                        {textFilter ? (
                            <button type="button" className="btn btn-sm btn-secondary" onClick={() => setTextFilter('')}>
                                Clear filter
                            </button>
                        ) : (
                            <button type="button" className="btn btn-sm btn-secondary" onClick={() => navigate('/library')}>
                                Open Library
                            </button>
                        )}
                    </EmptyState>
                ) : (
                    grouped.map(([detector, rows]) => (
                        <details key={detector} className="tq-group" open>
                            <summary className="tq-group-summary">
                                <ChevronDown size={14} className="tq-group-chevron" aria-hidden="true" />
                                <span className="tq-group-name">{detector}</span>
                                <span className="tq-group-count">{rows.length}</span>
                            </summary>
                            <div className="tq-group-rows">
                                {rows.map((f) => renderRow(f))}
                            </div>
                        </details>
                    ))
                )}

                {findingsQuery.hasNextPage ? (
                    <div className="tq-load-more">
                        <button
                            type="button"
                            className="btn btn-secondary"
                            disabled={findingsQuery.isFetchingNextPage}
                            onClick={() => findingsQuery.fetchNextPage()}
                        >
                            {findingsQuery.isFetchingNextPage ? 'Loading…' : 'Load next 200 findings'}
                        </button>
                    </div>
                ) : null}

                <p className="tq-hint">
                    <kbd>J</kbd>/<kbd>K</kbd> move · <kbd>Enter</kbd> open · <kbd>X</kbd> select ·{' '}
                    <kbd>A</kbd> approve variants · <kbd>F</kbd> flag · <kbd>S</kbd> skip ·{' '}
                    <kbd>U</kbd> undo · <kbd>/</kbd> filter · <kbd>?</kbd> all shortcuts
                </p>
            </div>
        </AppShell>
    );
}
