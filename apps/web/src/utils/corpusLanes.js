/** Corpus lane labels + order for Library Source facet. */

export const LANE_ORDER = [
    'ordinance',
    'customs',
    'sales_tax',
    'federal_excise',
    'finance',
    'tax_laws_amendment',
    'other_acts',
    'manual',
];

export const LANE_LABELS = {
    ordinance: 'Income Tax Ordinance',
    customs: 'Customs',
    sales_tax: 'Sales Tax',
    federal_excise: 'Federal Excise',
    finance: 'Finance Acts',
    tax_laws_amendment: 'Tax Laws Amendments',
    other_acts: 'Other Acts',
    manual: 'Manual',
};

export function laneLabel(lane) {
    if (!lane) return 'Unknown';
    return LANE_LABELS[lane] || lane;
}

export function documentLane(doc) {
    return doc?.corpus_lane || (doc?.source_type === 'acts_corpus' ? 'other_acts' : 'manual');
}
