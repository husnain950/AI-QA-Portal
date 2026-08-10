/**
 * Presentation helpers for the pipeline's own QA numbers.
 *
 * The gate lives upstream (Acts_fbr: body >= 99.99%, footnotes 100.000%, and every
 * invariant passing). Nothing here re-decides it -- `gate_ok` comes from the pipeline
 * run; these functions only choose how to say it.
 */

export const BODY_GATE = 99.99;
export const FOOTNOTE_GATE = 100.0;

/** 'pass' | 'fail' | 'unknown' — 'unknown' means nobody has measured this version. */
export function gateState(metrics) {
    if (!metrics) return 'unknown';
    if (metrics.gate_ok === true) return 'pass';
    if (metrics.gate_ok === false) return 'fail';

    const hasInvariants = Number.isFinite(metrics.invariants_total)
        && metrics.invariants_total > 0;
    if (hasInvariants) {
        return metrics.invariants_passed === metrics.invariants_total ? 'pass' : 'fail';
    }
    return 'unknown';
}

export function invariantLabel(metrics) {
    if (!metrics || !Number.isFinite(metrics.invariants_total)
        || metrics.invariants_total === 0) {
        return null;
    }
    return `${metrics.invariants_passed ?? 0}/${metrics.invariants_total}`;
}

/** Percentages are quoted to 3dp because the gate itself is (99.99 / 100.000). */
export function formatConserved(value) {
    if (!Number.isFinite(value)) return null;
    return `${value.toFixed(3)}%`;
}

export function conservationState(value, gate) {
    if (!Number.isFinite(value)) return 'unknown';
    return value >= gate ? 'pass' : 'fail';
}

/**
 * One-line summary for a document card. Returns null when nothing was measured, so the
 * UI can stay silent rather than implying a green run that never happened.
 */
export function healthSummary(metrics) {
    if (!metrics) return null;
    const parts = [];
    const invariants = invariantLabel(metrics);
    if (invariants) parts.push(`invariants ${invariants}`);

    const body = formatConserved(metrics.body_conserved);
    if (body) parts.push(`body ${body}`);

    const footnotes = formatConserved(metrics.footnote_conserved);
    if (footnotes) parts.push(`footnotes ${footnotes}`);

    return parts.length ? parts.join(' · ') : null;
}

/** Difference between two versions' measurements, for the "what did the fix buy us" line. */
export function metricsDelta(current, previous) {
    if (!current || !previous) return [];
    const rows = [];

    const invariantGain = (current.invariants_passed ?? 0) - (previous.invariants_passed ?? 0);
    if (invariantGain !== 0) {
        rows.push({
            label: 'invariants passing',
            delta: invariantGain,
            better: invariantGain > 0,
        });
    }

    for (const [key, label] of [
        ['body_conserved', 'body conserved'],
        ['footnote_conserved', 'footnotes conserved'],
    ]) {
        const before = previous[key];
        const after = current[key];
        if (!Number.isFinite(before) || !Number.isFinite(after)) continue;
        const delta = after - before;
        // Below a thousandth of a percent the gate cannot tell the difference either.
        if (Math.abs(delta) < 0.0005) continue;
        rows.push({
            label,
            delta: `${delta > 0 ? '+' : ''}${delta.toFixed(3)}%`,
            better: delta > 0,
        });
    }
    return rows;
}
