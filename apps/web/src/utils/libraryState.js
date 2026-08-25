import { DEFAULT_SORT, SORT_VALUES } from './documentFilters';
import { laneLabel } from './corpusLanes';

const KINDS = new Set(['native-digital', 'scanned-ocr', 'mixed-ocr']);
const HEALTH = new Set(['within_gate', 'outside_gate', 'unmeasured']);
const REVIEW = new Set(['complete', 'in_progress', 'untouched']);

const KIND_LABEL = {
    'native-digital': 'Native',
    'scanned-ocr': 'Scanned',
    'mixed-ocr': 'Mixed',
};
const HEALTH_LABEL = {
    within_gate: 'Within gate',
    outside_gate: 'Outside gate',
    unmeasured: 'Unmeasured',
};
const REVIEW_LABEL = {
    complete: 'Complete',
    in_progress: 'In progress',
    untouched: 'Untouched',
};

/**
 * Read Library discovery state from the page URL.
 * Unknown values are dropped rather than forwarded into filters.
 */
export function parseLibrarySearchParams(searchParams) {
    const kind = searchParams.get('kind') || '';
    const health = searchParams.get('health') || '';
    const review = searchParams.get('review') || '';
    const sortRaw = searchParams.get('sort') || '';
    const flaggedRaw = searchParams.get('flagged') || '';
    return {
        query: searchParams.get('q') || '',
        sort: SORT_VALUES.has(sortRaw) ? sortRaw : '',
        facets: {
            corpusLane: searchParams.get('lane') || '',
            sourceKind: KINDS.has(kind) ? kind : '',
            health: HEALTH.has(health) ? health : '',
            review: REVIEW.has(review) ? review : '',
            flagged: flaggedRaw === '1' || flaggedRaw === 'flagged' ? 'flagged' : '',
        },
    };
}

export function serializeLibrarySearchParams({ query = '', facets = {}, sort = DEFAULT_SORT } = {}) {
    const next = new URLSearchParams();
    const q = String(query || '').trim();
    if (q) next.set('q', q);
    if (facets.corpusLane) next.set('lane', facets.corpusLane);
    if (facets.sourceKind) next.set('kind', facets.sourceKind);
    if (facets.health) next.set('health', facets.health);
    if (facets.review) next.set('review', facets.review);
    if (facets.flagged) next.set('flagged', '1');
    if (sort && sort !== DEFAULT_SORT) next.set('sort', sort);
    return next;
}

export function libraryFilterChips({ query = '', facets = {} } = {}) {
    const chips = [];
    const q = String(query || '').trim();
    if (q) chips.push({ key: 'q', label: `\u201C${q}\u201D` });
    if (facets.corpusLane) {
        chips.push({ key: 'corpusLane', label: `Source: ${laneLabel(facets.corpusLane)}` });
    }
    if (facets.sourceKind) {
        chips.push({ key: 'sourceKind', label: KIND_LABEL[facets.sourceKind] || facets.sourceKind });
    }
    if (facets.health) {
        chips.push({ key: 'health', label: HEALTH_LABEL[facets.health] || facets.health });
    }
    if (facets.review) {
        chips.push({ key: 'review', label: REVIEW_LABEL[facets.review] || facets.review });
    }
    if (facets.flagged) {
        chips.push({ key: 'flagged', label: 'Flagged' });
    }
    return chips;
}
