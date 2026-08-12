import React from 'react';
import { provenancePills, provenanceTooltip } from '../../utils/documentTags';

/**
 * Colored provenance pills for Library cards and Review header.
 */
const DocumentTags = ({ provenance, compact = false }) => {
    const pills = provenancePills(provenance);
    if (!pills.length) return null;

    const tip = provenanceTooltip(provenance);

    return (
        <div className="document-tags" title={tip || undefined}>
            {pills.map((pill) => (
                <span
                    key={pill.code}
                    className={`document-tag ${pill.className}`}
                    title={pill.title}
                >
                    {compact ? pill.shortLabel : pill.label}
                </span>
            ))}
        </div>
    );
};

export default DocumentTags;
