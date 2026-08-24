import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import { gateState } from '../../utils/versionHealth';
import QualityMetrics from '../ui/QualityMetrics';

/**
 * The conversion pipeline's own verdict on the active parse.
 *
 * Renders nothing when no measurement has been ingested — an empty row is honest,
 * a green tick for an unmeasured document is not.
 */
const DocumentHealth = ({ health }) => {
    if (!health || !health.measured_at) return null;

    const state = gateState(health);

    return (
        <div className={`document-health document-health-${state}`}>
            <span className="document-health-gate">
                {state === 'pass' ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                {state === 'pass' ? 'within gate' : 'outside gate'}
            </span>

            <QualityMetrics metrics={health} classPrefix="document-health-metric" />
        </div>
    );
};

export default DocumentHealth;
