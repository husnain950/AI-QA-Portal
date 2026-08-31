/** Corpus lane labels + order for Library Source facet. */

export const LANE_ORDER = [
    'ordinance',
    'customs',
    'sales_tax',
    'federal_excise',
    'finance',
    'tax_laws_amendment',
    'other_acts',
    'income_tax_rules',
    'sales_tax_rules',
    'customs_rules',
    'federal_excise_rules',
    'other_rules',
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
    income_tax_rules: 'Income Tax Rules',
    sales_tax_rules: 'Sales Tax Rules',
    customs_rules: 'Customs Rules',
    federal_excise_rules: 'Federal Excise Rules',
    other_rules: 'Other Rules & Regulations',
    manual: 'Manual',
};

export function laneLabel(lane) {
    if (!lane) return 'Unknown';
    return LANE_LABELS[lane] || lane;
}

/**
 * The lane the SERVER resolved, which is the one the Library filters on.
 *
 * This used to re-derive it, and the derivation was a fraction of `LANE_SQL`: for a
 * row whose stored `corpus_lane` is NULL the server classifies by title while this
 * collapsed every one of them to `other_acts`. Filtering by Source = Customs
 * therefore returned a card badged "Other Acts" -- the filter and the label
 * disagreeing about the same row. The server now sends `lane`; the remaining
 * fallback is only for payloads that carry no lane at all (edition siblings,
 * findings rows), and it never contradicts a value that IS present.
 */
export function documentLane(doc) {
    return doc?.lane
        || doc?.corpus_lane
        || (doc?.source_type === 'acts_corpus' ? 'other_acts' : 'manual');
}
