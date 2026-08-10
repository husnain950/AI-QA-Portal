import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import {
    BODY_GATE,
    FOOTNOTE_GATE,
    conservationState,
    formatConserved,
    gateState,
    invariantLabel,
} from '../../utils/versionHealth';

/**
 * The conversion pipeline's own verdict on the active parse.
 *
 * Renders nothing when no measurement has been ingested — an empty row is honest,
 * a green tick for an unmeasured document is not.
 */
const DocumentHealth = ({ health }) => {
    if (!health || !health.measured_at) return null;

    const state = gateState(health);
    const invariants = invariantLabel(health);
    const body = formatConserved(health.body_conserved);
    const footnotes = formatConserved(health.footnote_conserved);

    return (
        <div className={`document-health document-health-${state}`}>
            <span className="document-health-gate">
                {state === 'pass' ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                {state === 'pass' ? 'within gate' : 'outside gate'}
            </span>

            {invariants && (
                <span
                    className={`document-health-metric document-health-${
                        health.invariants_passed === health.invariants_total ? 'pass' : 'fail'
                    }`}
                    title={
                        health.failing_invariants?.length
                            ? `Failing: ${health.failing_invariants.join(', ')}`
                            : 'Every invariant passes'
                    }
                >
                    invariants {invariants}
                </span>
            )}

            {body && (
                <span
                    className={`document-health-metric document-health-${conservationState(
                        health.body_conserved,
                        BODY_GATE,
                    )}`}
                    title={`Body text conserved (gate ${BODY_GATE}%) · ${
                        health.body_missing ?? 0
                    } words missing`}
                >
                    body {body}
                </span>
            )}

            {footnotes && (
                <span
                    className={`document-health-metric document-health-${conservationState(
                        health.footnote_conserved,
                        FOOTNOTE_GATE,
                    )}`}
                    title={`Footnote text conserved (gate ${FOOTNOTE_GATE}%) · ${
                        health.footnote_missing ?? 0
                    } words missing`}
                >
                    footnotes {footnotes}
                </span>
            )}
        </div>
    );
};

export default DocumentHealth;
