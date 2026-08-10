import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppShell from '../components/layout/AppShell';
import { api, getReviewerName, setReviewerName } from '../utils/api';
import { formatSectionLabel } from '../utils/tocLabels';
import { editionDateFromName } from '../utils/editions';
import { useUiStore } from '../stores/uiStore';

const TRIAGE_FILTERS = [
    { id: 'new', label: 'New' },
    { id: 'parse_bug', label: 'Parse bug' },
    { id: 'source_defect', label: 'Source defect' },
    { id: 'deliberate', label: 'Deliberate' },
    { id: 'not_a_defect', label: 'Not a defect' },
    { id: 'fixed', label: 'Fixed' },
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

export default function TriagePage() {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const pushToast = useUiStore((s) => s.pushToast);
    const promptDialog = useUiStore((s) => s.promptDialog);

    const [findings, setFindings] = useState([]);
    const [stats, setStats] = useState({ total: 0, done: 0, left: 0 });
    const [loading, setLoading] = useState(true);
    const [cursor, setCursor] = useState(0);
    const [skipped, setSkipped] = useState(() => new Set());
    const undoRef = useRef(null);
    const lastApproveRef = useRef(0);
    const rowRefs = useRef([]);

    const triageFilter = searchParams.get('triage') || 'new';
    const detectorFilter = searchParams.get('detector') || '';

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const qs = new URLSearchParams();
            if (triageFilter) qs.set('triage', triageFilter);
            if (detectorFilter) qs.set('detector', detectorFilter);
            const data = await api.get(`/findings?${qs.toString()}`);
            setFindings(data.findings || data.items || data || []);
            setStats(data.stats || {
                total: (data.findings || data || []).length,
                done: 0,
                left: (data.findings || data || []).length,
            });
        } catch (err) {
            pushToast({ type: 'error', message: err.message || 'Failed to load findings' });
            setFindings([]);
        } finally {
            setLoading(false);
        }
    }, [triageFilter, detectorFilter, pushToast]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        const name = getReviewerName();
        if (name === 'anonymous') {
            promptDialog({
                title: 'Reviewer name',
                message: 'Recorded on review_events via X-Reviewer (not authentication).',
                defaultValue: '',
                confirmLabel: 'Continue',
            }).then((v) => {
                if (v) setReviewerName(v);
            });
        }
    }, [promptDialog]);

    const visible = useMemo(
        () => findings.filter((f) => !skipped.has(f.id)),
        [findings, skipped],
    );

    const grouped = useMemo(() => {
        const map = groupBy(visible, (f) => f.detector || 'unknown');
        const entries = [...map.entries()].map(([detector, rows]) => {
            const sorted = [...rows].sort(
                (a, b) => (b.blast_radius || b.score || 0) - (a.blast_radius || a.score || 0),
            );
            return [detector, sorted];
        });
        entries.sort((a, b) => b[1].length - a[1].length);
        return entries;
    }, [visible]);

    const flat = useMemo(() => grouped.flatMap(([, rows]) => rows), [grouped]);

    useEffect(() => {
        if (cursor >= flat.length) setCursor(Math.max(0, flat.length - 1));
    }, [flat.length, cursor]);

    const active = flat[cursor] || null;

    const setTriage = async (finding, triage, note = '') => {
        const prev = { ...finding };
        setFindings((rows) =>
            rows.map((r) => (r.id === finding.id ? { ...r, triage } : r)),
        );
        try {
            await api.patch(`/findings/${finding.id}/status`, { triage, note });
            undoRef.current = async () => {
                await api.patch(`/findings/${finding.id}/status`, {
                    triage: prev.triage,
                    note: prev.triage_note || '',
                });
                await load();
            };
            pushToast({
                type: 'info',
                message: `Marked ${finding.detector} as ${triage}`,
                onUndo: () => undoRef.current?.(),
            });
            setCursor((c) => Math.min(c + 1, Math.max(0, flat.length - 1)));
        } catch (err) {
            setFindings((rows) =>
                rows.map((r) => (r.id === finding.id ? prev : r)),
            );
            pushToast({ type: 'error', message: err.message });
        }
    };

    const approveVariants = async (finding) => {
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
                await api.delete(`/variants/${encodeURIComponent(finding.variant_key)}/approve`);
                await load();
            };
            pushToast({
                type: 'info',
                message: `Approved ${n} identical leaves`,
                onUndo: () => undoRef.current?.(),
            });
            await setTriage(finding, 'not_a_defect', 'approved via variant');
        } catch (err) {
            pushToast({ type: 'error', message: err.message });
        }
    };

    useEffect(() => {
        const onKey = (e) => {
            if (e.target.matches('input, textarea, select') || e.target.isContentEditable) return;
            const f = flat[cursor];
            if (e.key === 'j') {
                e.preventDefault();
                setCursor((c) => Math.min(c + 1, Math.max(0, flat.length - 1)));
            } else if (e.key === 'k') {
                e.preventDefault();
                setCursor((c) => Math.max(0, c - 1));
            } else if (e.key === 'Enter' && f) {
                e.preventDefault();
                navigate(`/review/${f.document_id}/${f.section_id}?from=queue`);
            } else if (e.key === 'a' && f) {
                e.preventDefault();
                approveVariants(f);
            } else if (e.key === 'f' && f) {
                e.preventDefault();
                promptDialog({
                    title: 'Flag finding',
                    message: 'Disposition note (optional)',
                    defaultValue: '',
                    confirmLabel: 'Mark parse_bug',
                }).then((note) => {
                    if (note === null) return;
                    setTriage(f, 'parse_bug', note || '');
                });
            } else if (e.key === 's' && f) {
                e.preventDefault();
                setSkipped((prev) => new Set(prev).add(f.id));
                setCursor((c) => Math.min(c + 1, Math.max(0, flat.length - 1)));
            } else if (e.key === 'u') {
                e.preventDefault();
                undoRef.current?.();
            } else if (e.key === '/') {
                e.preventDefault();
                document.getElementById('tq-filter-input')?.focus();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [flat, cursor, navigate, promptDialog]);

    useEffect(() => {
        rowRefs.current[cursor]?.scrollIntoView({ block: 'nearest' });
    }, [cursor]);

    const toggleChip = (key, value) => {
        const next = new URLSearchParams(searchParams);
        if (!value || searchParams.get(key) === value) next.delete(key);
        else next.set(key, value);
        if (key === 'triage' && value) next.set('triage', value);
        setSearchParams(next);
    };

    return (
        <AppShell title="Triage" scrollable>
            <div className="tq-page">
                <div className="tq-header">
                    <div className="tq-burn">
                        <strong>{stats.total ?? findings.length}</strong> findings ·{' '}
                        <strong>{stats.done ?? 0}</strong> done ·{' '}
                        <strong>{stats.left ?? visible.length}</strong> left
                    </div>
                    <input
                        id="tq-filter-input"
                        placeholder="Filter detector…"
                        defaultValue={detectorFilter}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                const next = new URLSearchParams(searchParams);
                                const v = e.currentTarget.value.trim();
                                if (v) next.set('detector', v);
                                else next.delete('detector');
                                setSearchParams(next);
                            }
                        }}
                        style={{
                            padding: '6px 10px',
                            borderRadius: 6,
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-bg-primary)',
                            color: 'var(--color-text-primary)',
                            minWidth: 180,
                        }}
                    />
                </div>

                <div className="tq-filters">
                    {TRIAGE_FILTERS.map((f) => (
                        <button
                            key={f.id}
                            type="button"
                            className={`tq-chip ${triageFilter === f.id ? 'active' : ''}`}
                            onClick={() => toggleChip('triage', f.id)}
                        >
                            {f.label}
                        </button>
                    ))}
                </div>

                {loading ? (
                    <p className="tq-meta">Loading findings…</p>
                ) : flat.length === 0 ? (
                    <p className="tq-meta">No findings in this filter. Run sync with detectors, or open Library.</p>
                ) : (
                    grouped.map(([detector, rows]) => (
                        <details key={detector} className="tq-group" open>
                            <summary className="tq-group-summary">
                                <span>{detector}</span>
                                <span className="tq-meta">{rows.length}</span>
                            </summary>
                            {rows.map((f) => {
                                const idx = flat.indexOf(f);
                                const ed = editionDateFromName(f.document_name || '');
                                const label = formatSectionLabel(f.section_code, f.section_heading);
                                return (
                                    <div key={f.id}>
                                        <div
                                            ref={(el) => {
                                                rowRefs.current[idx] = el;
                                            }}
                                            className={`tq-row ${idx === cursor ? 'active' : ''}`}
                                            onClick={() => setCursor(idx)}
                                        >
                                            <details>
                                                <summary style={{ cursor: 'pointer' }}>▸</summary>
                                            </details>
                                            <div className="tq-row-main">
                                                <span className="tq-detector">{f.detector}</span>
                                                <span>
                                                    {f.family_label || f.family_key || 'Statute'} · {label}
                                                </span>
                                                {f.cross_family ? (
                                                    <span className="tq-cross-family">cross-family</span>
                                                ) : null}
                                                <span className="tq-meta">
                                                    {f.blast_radius || 1} edition{(f.blast_radius || 1) === 1 ? '' : 's'}
                                                    {' · '}
                                                    {ed.label}
                                                    {f.start_page != null ? ` · p.${f.start_page}` : ''}
                                                    {f.summary ? ` · ${f.summary}` : ''}
                                                </span>
                                            </div>
                                            <span className="tq-blast">{Math.round(f.score || 0)}</span>
                                        </div>
                                        <div className="tq-expand">
                                            {(f.editions || []).length ? (
                                                (f.editions || []).map((edRow) => (
                                                    <div key={edRow.section_id} className="tq-edition-row">
                                                        <span>{edRow.document_name}</span>
                                                        <span className="tq-meta">{edRow.review_status}</span>
                                                        <button
                                                            type="button"
                                                            className="btn btn-secondary"
                                                            style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                                                            onClick={() =>
                                                                navigate(
                                                                    `/review/${edRow.document_id}/${edRow.section_id}?from=queue`,
                                                                )
                                                            }
                                                        >
                                                            open
                                                        </button>
                                                    </div>
                                                ))
                                            ) : (
                                                <p>
                                                    {f.detail?.assertion
                                                        || 'Open the leaf to inspect. Approving the variant covers identical output across editions.'}
                                                </p>
                                            )}
                                            {f.variant_key ? (
                                                <p className="tq-meta">
                                                    variant {String(f.variant_key).slice(0, 12)}…
                                                    {' · '}
                                                    <button
                                                        type="button"
                                                        className="btn btn-secondary"
                                                        style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                                                        onClick={() =>
                                                            navigate(
                                                                `/timeline/${encodeURIComponent(f.family_key || 'x')}/${encodeURIComponent(f.section_code || '')}`,
                                                            )
                                                        }
                                                    >
                                                        timeline
                                                    </button>
                                                </p>
                                            ) : null}
                                        </div>
                                    </div>
                                );
                            })}
                        </details>
                    ))
                )}

                <p className="tq-hint">
                    j/k move · Enter open · a approve-variants · f flag · s skip · u undo · / filter
                </p>
            </div>
        </AppShell>
    );
}
