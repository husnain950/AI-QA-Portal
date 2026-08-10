import React from 'react';
import { Loader2 } from 'lucide-react';

/**
 * Shared diff renderer. Accepts either:
 * - version-panel shape: { base, target, summary, sections, note }
 * - timeline shape: { lines: string[] } or string[]
 */
export default function DiffView({ diff, loading }) {
    if (loading) {
        return (
            <p className="version-diff-empty">
                <Loader2 size={14} className="spin" /> Comparing…
            </p>
        );
    }
    if (!diff) return null;

    if (Array.isArray(diff)) {
        return <LineDiff lines={diff} />;
    }
    if (Array.isArray(diff.lines)) {
        return <LineDiff lines={diff.lines} />;
    }

    if (!diff.base) {
        return <p className="version-diff-empty">{diff.note}</p>;
    }
    const { added, removed, changed, unchanged } = diff.summary || {};
    return (
        <div className="version-diff">
            <p className="version-diff-summary">
                v{diff.base.version_no} → v{diff.target.version_no}:{' '}
                <strong>{changed}</strong> changed, <strong>{added}</strong> added,{' '}
                <strong>{removed}</strong> removed, {unchanged} unchanged
            </p>
            {diff.sections.length === 0 && (
                <p className="version-diff-empty">These versions parse identically.</p>
            )}
            {diff.sections.map((section) => (
                <div key={section.source_key} className="version-diff-section">
                    <h5>
                        <span className={`diff-badge diff-${section.change}`}>
                            {section.change}
                        </span>
                        {section.section_code ? `${section.section_code}. ` : ''}
                        {section.section_heading || section.source_key}
                        {section.start_page ? (
                            <em> · p.{section.start_page}</em>
                        ) : null}
                    </h5>
                    {section.diff.length > 0 && <LineDiff lines={section.diff} />}
                </div>
            ))}
        </div>
    );
}

function LineDiff({ lines }) {
    return (
        <pre className="version-diff-body">
            {lines.map((line, index) => (
                <span
                    key={index}
                    className={
                        line.startsWith('+')
                            ? 'diff-add'
                            : line.startsWith('-')
                              ? 'diff-del'
                              : line.startsWith('@@')
                                ? 'diff-hunk'
                                : ''
                    }
                >
                    {line}
                    {'\n'}
                </span>
            ))}
        </pre>
    );
}
