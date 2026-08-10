import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import AppShell from '../components/layout/AppShell';
import DiffView from '../components/diff/DiffView';
import { api } from '../utils/api';
import { formatSectionLabel } from '../utils/tocLabels';

export default function TimelinePage() {
    const { family, sectionCode } = useParams();
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [openDiff, setOpenDiff] = useState(null);
    const [qFamily, setQFamily] = useState(family || '');
    const [qCode, setQCode] = useState(sectionCode || '');

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const res = await api.get(
                    `/timeline/${encodeURIComponent(family)}/${encodeURIComponent(sectionCode)}`,
                );
                if (!cancelled) setData(res);
            } catch (err) {
                if (!cancelled) setError(err.message || 'Failed to load timeline');
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
                <form
                    className="tl-search"
                    onSubmit={(e) => {
                        e.preventDefault();
                        if (qFamily && qCode) {
                            navigate(`/timeline/${encodeURIComponent(qFamily)}/${encodeURIComponent(qCode)}`);
                        }
                    }}
                >
                    <input
                        value={qFamily}
                        onChange={(e) => setQFamily(e.target.value)}
                        placeholder="Family key (e.: customs act 1969)"
                    />
                    <input
                        value={qCode}
                        onChange={(e) => setQCode(e.target.value)}
                        placeholder="Section code"
                    />
                    <button type="submit" className="btn btn-primary">Go</button>
                </form>

                <h1 className="tl-title">
                    {data?.family_label || family} ·{' '}
                    {formatSectionLabel(sectionCode, data?.section_heading)}
                </h1>
                <p className="tl-sub">Edition changelog — runs of identical text collapse into one band.</p>

                {error ? <p className="tl-warn">{error}</p> : null}

                <ul className="tl-spine">
                    {events.map((ev, i) => (
                        <li
                            key={`${ev.year}-${i}`}
                            className={`tl-event ${ev.kind === 'unchanged' ? 'unchanged' : ''}`}
                        >
                            <span className="tl-year">{ev.year_label || ev.year || 'year unknown'}</span>
                            <span>
                                {ev.kind === 'unchanged'
                                    ? `unchanged · ${ev.count || 1} editions ${ev.span || ''}`
                                    : ev.kind === 'first'
                                        ? 'first edition'
                                        : ev.kind === 'markup_only'
                                            ? 'markup-only change'
                                            : 'changed'}
                            </span>
                            {ev.word_delta ? (
                                <span className="tq-meta"> {ev.word_delta}</span>
                            ) : null}
                            {ev.missing_in?.length ? (
                                <div className="tl-warn">⚠ missing in {ev.missing_in.join(', ')}</div>
                            ) : null}
                            {ev.diff ? (
                                <div style={{ marginTop: 8 }}>
                                    <button
                                        type="button"
                                        className="btn btn-secondary"
                                        style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                                        onClick={() => setOpenDiff(openDiff === i ? null : i)}
                                    >
                                        {openDiff === i ? 'hide diff' : 'show diff'}
                                    </button>
                                    {openDiff === i ? <DiffView diff={ev.diff} /> : null}
                                </div>
                            ) : null}
                            {ev.document_id && ev.section_id ? (
                                <div style={{ marginTop: 6 }}>
                                    <button
                                        type="button"
                                        className="btn btn-secondary"
                                        style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                                        onClick={() =>
                                            navigate(`/review/${ev.document_id}/${ev.section_id}`)
                                        }
                                    >
                                        open
                                    </button>
                                </div>
                            ) : null}
                        </li>
                    ))}
                </ul>
            </div>
        </AppShell>
    );
}
