import React, { useCallback, useEffect, useState } from 'react';
import {
    AlertTriangle,
    CheckCircle2,
    FileClock,
    History,
    Loader2,
    RotateCcw,
    X,
} from 'lucide-react';

import { versionsApi } from '../../utils/api';
import DiffView from '../diff/DiffView';
import { useUiStore } from '../../stores/uiStore';
import {
    BODY_GATE,
    FOOTNOTE_GATE,
    conservationState,
    formatConserved,
    gateState,
    invariantLabel,
    metricsDelta,
} from '../../utils/versionHealth';

const formatWhen = (value) => {
    if (!value) return '';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

/** The carry-over report the ingest returned, phrased for a reviewer. */
const CarryoverSummary = ({ stats }) => {
    if (!stats) return null;
    const rows = [
        ['leaves changed', stats.sections_changed],
        ['leaves added', stats.sections_added],
        ['leaves removed', stats.sections_removed],
        ['findings re-anchored', stats.reanchored],
        ['findings needing recheck', stats.needs_recheck],
        ['findings orphaned', stats.orphaned],
        ['approvals reset', stats.approvals_reset],
        ['approvals lost with removed leaves', stats.approvals_lost],
    ].filter(([, value]) => Number(value) > 0);

    if (!rows.length) {
        return <p className="version-carryover-empty">No review state was affected.</p>;
    }
    return (
        <ul className="version-carryover">
            {rows.map(([label, value]) => (
                <li key={label}>
                    <strong>{value}</strong> {label}
                </li>
            ))}
        </ul>
    );
};

const MetricsRow = ({ metrics }) => {
    if (!metrics) {
        return <span className="version-metric version-metric-unknown">not measured</span>;
    }
    const invariants = invariantLabel(metrics);
    const body = formatConserved(metrics.body_conserved);
    const footnotes = formatConserved(metrics.footnote_conserved);

    return (
        <div className="version-metrics">
            {invariants && (
                <span
                    className={`version-metric version-metric-${
                        metrics.invariants_passed === metrics.invariants_total
                            ? 'pass'
                            : 'fail'
                    }`}
                    title={
                        metrics.failing_invariants?.length
                            ? `Failing: ${metrics.failing_invariants.join(', ')}`
                            : 'All invariants pass'
                    }
                >
                    invariants {invariants}
                </span>
            )}
            {body && (
                <span
                    className={`version-metric version-metric-${conservationState(
                        metrics.body_conserved,
                        BODY_GATE,
                    )}`}
                    title={`Gate is ${BODY_GATE}% · ${metrics.body_missing ?? 0} words missing`}
                >
                    body {body}
                </span>
            )}
            {footnotes && (
                <span
                    className={`version-metric version-metric-${conservationState(
                        metrics.footnote_conserved,
                        FOOTNOTE_GATE,
                    )}`}
                    title={`Gate is ${FOOTNOTE_GATE}% · ${
                        metrics.footnote_missing ?? 0
                    } words missing`}
                >
                    footnotes {footnotes}
                </span>
            )}
        </div>
    );
};

/**
 * Version history for a document: what each JSON parse cost in review state, what the
 * pipeline measured for it, what changed against the previous one, and a way back.
 */
const VersionPanel = ({ documentId, open, onClose, onChanged }) => {
    const confirmDialog = useUiStore((s) => s.confirmDialog);
    const [versions, setVersions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [selectedId, setSelectedId] = useState(null);
    const [diff, setDiff] = useState(null);
    const [diffLoading, setDiffLoading] = useState(false);
    const [busyId, setBusyId] = useState(null);

    const load = useCallback(async () => {
        if (!documentId) return;
        setLoading(true);
        setError('');
        try {
            setVersions(await versionsApi.list(documentId));
        } catch (err) {
            setError(err.message || 'Could not load version history');
        } finally {
            setLoading(false);
        }
    }, [documentId]);

    useEffect(() => {
        if (open) load();
    }, [open, load]);

    const showDiff = async (version) => {
        if (selectedId === version.id) {
            setSelectedId(null);
            setDiff(null);
            return;
        }
        setSelectedId(version.id);
        setDiff(null);
        setDiffLoading(true);
        try {
            setDiff(await versionsApi.diff(documentId, version.id));
        } catch (err) {
            setError(err.message || 'Could not build the diff');
        } finally {
            setDiffLoading(false);
        }
    };

    const activate = async (version) => {
        const confirmed = await confirmDialog({
            title: `Make version ${version.version_no} active?`,
            message:
                'The stored JSON is re-applied through the same ingest as any other '
                + 'version, so findings are carried across it the same way.',
            confirmLabel: 'Activate',
        });
        if (!confirmed) return;
        setBusyId(version.id);
        setError('');
        try {
            await versionsApi.activate(documentId, version.id);
            await load();
            onChanged?.();
        } catch (err) {
            setError(err.message || 'Could not activate that version');
        } finally {
            setBusyId(null);
        }
    };

    if (!open) return null;

    return (
        <aside className="version-panel" aria-label="Version history">
            <header className="version-panel-header">
                <h3>
                    <History size={16} /> JSON versions
                </h3>
                <button type="button" onClick={onClose} aria-label="Close version history">
                    <X size={16} />
                </button>
            </header>

            <p className="version-panel-hint">
                The PDF is fixed. Each entry is a parse of it — push a corrected JSON
                without re-uploading the source.
            </p>

            {error && <p className="version-panel-error">{error}</p>}
            {loading && (
                <p className="version-diff-empty">
                    <Loader2 size={14} className="spin" /> Loading…
                </p>
            )}

            <ol className="version-list">
                {versions.map((version, index) => {
                    const previous = versions[index + 1];
                    const delta = metricsDelta(version.metrics, previous?.metrics);
                    const state = gateState(version.metrics);
                    return (
                        <li
                            key={version.id}
                            className={`version-item${version.is_active ? ' is-active' : ''}`}
                        >
                            <div className="version-item-head">
                                <span className="version-no">v{version.version_no}</span>
                                {version.is_active && (
                                    <span className="version-active-badge">
                                        <CheckCircle2 size={12} /> active
                                    </span>
                                )}
                                {state === 'fail' && (
                                    <span
                                        className="version-gate-badge version-gate-fail"
                                        title="Outside the pipeline's QA gate"
                                    >
                                        <AlertTriangle size={12} /> gate
                                    </span>
                                )}
                                <span className="version-when">
                                    {formatWhen(version.created_at)}
                                </span>
                            </div>

                            {version.note && <p className="version-note">{version.note}</p>}
                            <p className="version-meta">
                                {version.total_sections} sections
                                {version.created_by ? ` · by ${version.created_by}` : ''}
                                {version.source_name ? ` · ${version.source_name}` : ''}
                            </p>

                            <MetricsRow metrics={version.metrics} />

                            {delta.length > 0 && (
                                <ul className="version-delta">
                                    {delta.map((row) => (
                                        <li
                                            key={row.label}
                                            className={row.better ? 'better' : 'worse'}
                                        >
                                            {row.label} {row.delta > 0 ? '+' : ''}
                                            {row.delta}
                                        </li>
                                    ))}
                                </ul>
                            )}

                            <CarryoverSummary stats={version.stats} />

                            <div className="version-actions">
                                <button type="button" onClick={() => showDiff(version)}>
                                    <FileClock size={13} />
                                    {selectedId === version.id
                                        ? 'Hide changes'
                                        : 'What changed'}
                                </button>
                                {!version.is_active && (
                                    <button
                                        type="button"
                                        onClick={() => activate(version)}
                                        disabled={busyId === version.id}
                                    >
                                        {busyId === version.id ? (
                                            <Loader2 size={13} className="spin" />
                                        ) : (
                                            <RotateCcw size={13} />
                                        )}
                                        Make active
                                    </button>
                                )}
                            </div>

                            {selectedId === version.id && (
                                <DiffView diff={diff} loading={diffLoading} />
                            )}
                        </li>
                    );
                })}
            </ol>

            {!loading && versions.length === 0 && (
                <p className="version-diff-empty">No versions recorded yet.</p>
            )}
        </aside>
    );
};

export default VersionPanel;
