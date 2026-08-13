import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GitBranch, ExternalLink, AlertTriangle, Loader2 } from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import DiffView from '../components/diff/DiffView';
import EmptyState from '../components/ui/EmptyState';
import StatusChip from '../components/ui/StatusChip';
import { api } from '../utils/api';
import { formatSectionLabel } from '../utils/tocLabels';

const EVENT_LABELS = {
    unchanged: 'Unchanged',
    first: 'First edition',
    markup_only: 'Markup-only change',
    changed: 'Changed',
};

const EVENT_TONES = {
    unchanged: 'neutral',
    first: 'accent',
    markup_only: 'info',
    changed: 'warning',
};

export default function TimelinePage() {
    const { family, sectionCode } = useParams();
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [openDiff, setOpenDiff] = useState(null);
    const [qFamily, setQFamily] = useState(family || '');
    const [qCode, setQCode] = useState(sectionCode || '');

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError('');
        (async () => {
            try {
                const res = await api.get(
                    `/timeline/${encodeURIComponent(family)}/${encodeURIComponent(sectionCode)}`,
                );
                if (!cancelled) setData(res);
            } catch (err) {
                if (!cancelled) setError(err.message || 'Failed to load timeline');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [family, sectionCode]);

    const events = data?.events || [];

    return (
        <AppShell title="Timeline" scrollable showBackButton backTo="/">
            <div className="tl-page">
                <header className="tl-header">
                    <div>
                        <h1 className="tl-title">
                            <GitBranch size={18} aria-hidden="true" />
                            {data?.family_label || family} ·{' '}
                            {formatSectionLabel(sectionCode, data?.section_heading)}
                        </h1>
                        <p className="tl-sub">
                            Edition changelog — runs of identical text collapse into one band.
                        </p>
                    </div>
                    <form
                        className="tl-search"
                        onSubmit={(e) => {
                            e.preventDefault();
                            if (qFamily && qCode) {
                                navigate(`/timeline/${encodeURIComponent(qFamily)}/${encodeURIComponent(qCode)}`);
                            }
                        }}
                    >
                        <label className="sr-only" htmlFor="tl-family">Family key</label>
                        <input
                            id="tl-family"
                            className="ui-input"
                            value={qFamily}
                            onChange={(e) => setQFamily(e.target.value)}
                            placeholder="Family key (e.g. customs act 1969)"
                        />
                        <label className="sr-only" htmlFor="tl-code">Section code</label>
                        <input
                            id="tl-code"
                            className="ui-input tl-code-input"
                            value={qCode}
                            onChange={(e) => setQCode(e.target.value)}
                            placeholder="Section code"
                        />
                        <button type="submit" className="btn btn-sm btn-primary">Go</button>
                    </form>
                </header>

                {loading ? (
                    <div className="tl-loading">
                        <Loader2 className="animate-spin" size={22} style={{ color: 'var(--color-accent)' }} />
                        <span>Loading timeline…</span>
                    </div>
                ) : error ? (
                    <EmptyState
                        icon={<AlertTriangle size={36} />}
                        title="Could not load this timeline"
                        message={error}
                    />
                ) : events.length === 0 ? (
                    <EmptyState
                        icon={<GitBranch size={36} />}
                        title="No timeline events"
                        message="No editions of this section were found. Check the family key and section code."
                    />
                ) : (
                    <ul className="tl-spine">
                        {events.map((ev, i) => (
                            <li
                                key={`${ev.year}-${i}`}
                                className={`tl-event ${ev.kind === 'unchanged' ? 'unchanged' : ''}`}
                            >
                                <div className="tl-event-head">
                                    <span className="tl-year">{ev.year_label || ev.year || 'Year unknown'}</span>
                                    <StatusChip tone={EVENT_TONES[ev.kind] || 'warning'}>
                                        {ev.kind === 'unchanged'
                                            ? `Unchanged · ${ev.count || 1} editions ${ev.span || ''}`
                                            : EVENT_LABELS[ev.kind] || 'Changed'}
                                    </StatusChip>
                                    {ev.word_delta ? (
                                        <span className="tl-delta">{ev.word_delta}</span>
                                    ) : null}
                                    <span className="tl-event-actions">
                                        {ev.diff ? (
                                            <button
                                                type="button"
                                                className="btn btn-xs btn-secondary"
                                                onClick={() => setOpenDiff(openDiff === i ? null : i)}
                                            >
                                                {openDiff === i ? 'Hide diff' : 'Show diff'}
                                            </button>
                                        ) : null}
                                        {ev.document_id && ev.section_id ? (
                                            <button
                                                type="button"
                                                className="btn btn-xs btn-secondary"
                                                title="Open this edition in review"
                                                onClick={() =>
                                                    navigate(`/review/${ev.document_id}/${ev.section_id}`)
                                                }
                                            >
                                                <ExternalLink size={12} />
                                                Open
                                            </button>
                                        ) : null}
                                    </span>
                                </div>
                                {ev.missing_in?.length ? (
                                    <div className="tl-warn">
                                        <AlertTriangle size={12} aria-hidden="true" />
                                        Missing in {ev.missing_in.join(', ')}
                                    </div>
                                ) : null}
                                {ev.diff && openDiff === i ? <DiffView diff={ev.diff} /> : null}
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </AppShell>
    );
}
