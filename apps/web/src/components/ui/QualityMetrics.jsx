import React from 'react';

import {
    BODY_GATE,
    FOOTNOTE_GATE,
    conservationState,
    formatConserved,
    invariantLabel,
} from '../../utils/versionHealth';

/**
 * The pipeline's three measurements of a parse: invariants, body conservation,
 * footnote conservation.
 *
 * `DocumentHealth` and `VersionPanel` each rendered this row in full, with the same
 * state logic and the same three spans, differing only in a CSS class prefix and in
 * the wording of the tooltips. The two views keep their own styling via `classPrefix`;
 * the tooltips are now one wording, since they describe the same number.
 */
export default function QualityMetrics({ metrics, classPrefix }) {
    if (!metrics) return null;

    const invariants = invariantLabel(metrics);
    const body = formatConserved(metrics.body_conserved);
    const footnotes = formatConserved(metrics.footnote_conserved);
    const metricClass = (state) => `${classPrefix} ${classPrefix}-${state}`;

    return (
        <>
            {invariants && (
                <span
                    className={metricClass(
                        metrics.invariants_passed === metrics.invariants_total ? 'pass' : 'fail',
                    )}
                    title={
                        metrics.failing_invariants?.length
                            ? `Failing: ${metrics.failing_invariants.join(', ')}`
                            : 'Every invariant passes'
                    }
                >
                    invariants {invariants}
                </span>
            )}
            {body && (
                <span
                    className={metricClass(conservationState(metrics.body_conserved, BODY_GATE))}
                    title={`Body text conserved (gate ${BODY_GATE}%) · ${
                        metrics.body_missing ?? 0
                    } words missing`}
                >
                    body {body}
                </span>
            )}
            {footnotes && (
                <span
                    className={metricClass(
                        conservationState(metrics.footnote_conserved, FOOTNOTE_GATE),
                    )}
                    title={`Footnote text conserved (gate ${FOOTNOTE_GATE}%) · ${
                        metrics.footnote_missing ?? 0
                    } words missing`}
                >
                    footnotes {footnotes}
                </span>
            )}
        </>
    );
}
