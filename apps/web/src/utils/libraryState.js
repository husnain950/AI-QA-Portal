/** Library discovery state <-> URL search params.
 *
 * The URL is the single source of truth for the Library toolbar: every filter,
 * sort, view, and the search text round-trip through here so a filtered library
 * is a shareable link. Unknown values are dropped, never forwarded to the API.
 * Legacy single-value params (`lane=acts`, `kind=scanned-ocr`) parse into the
 * multi-value shape so older links keep working.
 */
import { LANE_ORDER } from './corpusLanes';
import { laneLabel } from './corpusLanes';
import {
    ADDED_PRESETS,
    DEFAULT_SORT,
    HEALTH_LABELS,
    KIND_LABELS,
    REVIEW_LABELS,
    SORT_VALUES,
    VIEW_VALUES,
    tagLabel,
} from './libraryQuery';

const LANES = new Set(LANE_ORDER);
const KINDS = new Set(['native-digital', 'scanned-ocr', 'mixed-ocr', 'unknown']);
const HEALTH = new Set(['within_gate', 'outside_gate', 'unmeasured']);
const REVIEW = new Set(['complete', 'in_progress', 'untouched']);
const ADDED_PRESET_VALUES = new Set(ADDED_PRESETS.map((preset) => preset.value));
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TAG_RE = /^[a-z0-9][a-z0-9-]{0,49}$/;

export const EMPTY_FACETS = {
    lanes: [],
    kinds: [],
    health: [],
    review: [],
    flagged: false,
    annotations: false,
    years: [],
    yearFrom: null,
    yearTo: null,
    addedPreset: '',
    addedAfter: '',
    addedBefore: '',
    pagesMin: null,
    pagesMax: null,
    tags: [],
};

function csv(raw) {
    return String(raw || '').split(',').map((part) => part.trim()).filter(Boolean);
}

function intOrNull(raw) {
    if (raw == null || raw === '') return null;
    const value = Number(raw);
    return Number.isInteger(value) && value >= 0 ? value : null;
}

/** Read Library discovery state from the page URL. */
export function parseLibrarySearchParams(searchParams) {
    const sortRaw = searchParams.get('sort') || '';
    const viewRaw = searchParams.get('view') || '';
    const flaggedRaw = searchParams.get('flagged') || '';
    const annotationsRaw = searchParams.get('annotations') || '';
    const addedPresetRaw = searchParams.get('added') || '';
    const addedAfterRaw = searchParams.get('added_after') || '';
    const addedBeforeRaw = searchParams.get('added_before') || '';
    return {
        query: searchParams.get('q') || '',
        sort: SORT_VALUES.has(sortRaw) ? sortRaw : '',
        view: VIEW_VALUES.has(viewRaw) ? viewRaw : 'all',
        group: searchParams.get('group') !== '0',
        facets: {
            lanes: csv(searchParams.get('lane')).filter((lane) => LANES.has(lane)),
            kinds: csv(searchParams.get('kind')).filter((kind) => KINDS.has(kind)),
            health: csv(searchParams.get('health')).filter((value) => HEALTH.has(value)),
            review: csv(searchParams.get('review')).filter((value) => REVIEW.has(value)),
            flagged: ['1', 'true', 'flagged'].includes(flaggedRaw),
            annotations: ['1', 'true'].includes(annotationsRaw),
            years: csv(searchParams.get('year'))
                .filter((year) => /^\d{4}$/.test(year))
                .map(Number),
            yearFrom: intOrNull(searchParams.get('year_from')),
            yearTo: intOrNull(searchParams.get('year_to')),
            addedPreset: ADDED_PRESET_VALUES.has(addedPresetRaw) ? addedPresetRaw : '',
            addedAfter: DATE_RE.test(addedAfterRaw) ? addedAfterRaw : '',
            addedBefore: DATE_RE.test(addedBeforeRaw) ? addedBeforeRaw : '',
            pagesMin: intOrNull(searchParams.get('pages_min')),
            pagesMax: intOrNull(searchParams.get('pages_max')),
            tags: csv(searchParams.get('tag')).filter((tag) => TAG_RE.test(tag)),
        },
    };
}

export function serializeLibrarySearchParams({
    query = '', facets = EMPTY_FACETS, sort = DEFAULT_SORT, view = 'all', group = true,
} = {}) {
    const next = new URLSearchParams();
    const q = String(query || '').trim();
    if (q) next.set('q', q);
    if (facets.lanes.length) next.set('lane', facets.lanes.join(','));
    if (facets.kinds.length) next.set('kind', facets.kinds.join(','));
    if (facets.health.length) next.set('health', facets.health.join(','));
    if (facets.review.length) next.set('review', facets.review.join(','));
    if (facets.flagged) next.set('flagged', '1');
    if (facets.annotations) next.set('annotations', '1');
    if (facets.years.length) next.set('year', facets.years.join(','));
    if (facets.yearFrom != null) next.set('year_from', String(facets.yearFrom));
    if (facets.yearTo != null) next.set('year_to', String(facets.yearTo));
    if (facets.addedPreset) next.set('added', facets.addedPreset);
    if (facets.addedAfter) next.set('added_after', facets.addedAfter);
    if (facets.addedBefore) next.set('added_before', facets.addedBefore);
    if (facets.pagesMin != null) next.set('pages_min', String(facets.pagesMin));
    if (facets.pagesMax != null) next.set('pages_max', String(facets.pagesMax));
    if (facets.tags.length) next.set('tag', facets.tags.join(','));
    if (view && view !== 'all') next.set('view', view);
    if (sort && sort !== DEFAULT_SORT) next.set('sort', sort);
    if (!group) next.set('group', '0');
    return next;
}

export function hasActiveFilters({ query = '', facets = EMPTY_FACETS, view = 'all' } = {}) {
    return Boolean(
        String(query || '').trim()
        || view !== 'all'
        || facets.lanes.length || facets.kinds.length || facets.health.length
        || facets.review.length || facets.tags.length
        || facets.flagged || facets.annotations
        || facets.years.length || facets.yearFrom != null || facets.yearTo != null
        || facets.addedPreset || facets.addedAfter || facets.addedBefore
        || facets.pagesMin != null || facets.pagesMax != null,
    );
}

const VIEW_LABELS = { favorites: 'Favorites', recent: 'Recently viewed' };

/** Human-readable chips for every active filter, in a stable order. */
export function libraryFilterChips({ query = '', facets = EMPTY_FACETS, view = 'all' } = {}) {
    const chips = [];
    const q = String(query || '').trim();
    if (view !== 'all') chips.push({ key: 'view', label: `View: ${VIEW_LABELS[view] || view}` });
    if (q) chips.push({ key: 'q', label: `“${q}”` });
    for (const lane of facets.lanes) {
        chips.push({ key: `lane:${lane}`, label: `Source: ${laneLabel(lane)}` });
    }
    for (const kind of facets.kinds) {
        chips.push({ key: `kind:${kind}`, label: `Format: ${KIND_LABELS[kind] || kind}` });
    }
    for (const value of facets.review) {
        chips.push({ key: `review:${value}`, label: `Review: ${REVIEW_LABELS[value] || value}` });
    }
    for (const value of facets.health) {
        chips.push({ key: `health:${value}`, label: `Health: ${HEALTH_LABELS[value] || value}` });
    }
    if (facets.flagged) chips.push({ key: 'flagged', label: 'Flagged sections' });
    if (facets.annotations) chips.push({ key: 'annotations', label: 'Open annotations' });
    for (const year of facets.years) {
        chips.push({ key: `year:${year}`, label: `Year: ${year}` });
    }
    if (facets.yearFrom != null || facets.yearTo != null) {
        const from = facets.yearFrom ?? '…';
        const to = facets.yearTo ?? '…';
        chips.push({ key: 'yearRange', label: `Year: ${from} – ${to}` });
    }
    if (facets.addedPreset) {
        const preset = ADDED_PRESETS.find((entry) => entry.value === facets.addedPreset);
        chips.push({ key: 'added', label: `Added: ${preset?.label || facets.addedPreset}` });
    } else if (facets.addedAfter || facets.addedBefore) {
        const after = facets.addedAfter || '…';
        const before = facets.addedBefore || '…';
        chips.push({ key: 'added', label: `Added: ${after} – ${before}` });
    }
    if (facets.pagesMin != null || facets.pagesMax != null) {
        const min = facets.pagesMin ?? 0;
        const max = facets.pagesMax ?? '∞';
        chips.push({ key: 'pages', label: `Pages: ${min} – ${max}` });
    }
    for (const tag of facets.tags) {
        chips.push({ key: `tag:${tag}`, label: `Tag: ${tagLabel(tag)}` });
    }
    return chips;
}

/** Return a new state with one chip's worth of filtering removed. */
export function clearChip(state, key) {
    const facets = { ...EMPTY_FACETS, ...state.facets };
    if (key === 'q') return { ...state, query: '' };
    if (key === 'view') return { ...state, view: 'all' };
    if (key === 'flagged') return { ...state, facets: { ...facets, flagged: false } };
    if (key === 'annotations') return { ...state, facets: { ...facets, annotations: false } };
    if (key === 'yearRange') {
        return { ...state, facets: { ...facets, yearFrom: null, yearTo: null } };
    }
    if (key === 'added') {
        return { ...state, facets: { ...facets, addedPreset: '', addedAfter: '', addedBefore: '' } };
    }
    if (key === 'pages') {
        return { ...state, facets: { ...facets, pagesMin: null, pagesMax: null } };
    }
    const [dimension, value] = key.split(':');
    if (dimension === 'lane') return { ...state, facets: { ...facets, lanes: facets.lanes.filter((v) => v !== value) } };
    if (dimension === 'kind') return { ...state, facets: { ...facets, kinds: facets.kinds.filter((v) => v !== value) } };
    if (dimension === 'health') return { ...state, facets: { ...facets, health: facets.health.filter((v) => v !== value) } };
    if (dimension === 'review') return { ...state, facets: { ...facets, review: facets.review.filter((v) => v !== value) } };
    if (dimension === 'year') {
        return { ...state, facets: { ...facets, years: facets.years.filter((v) => v !== Number(value)) } };
    }
    if (dimension === 'tag') return { ...state, facets: { ...facets, tags: facets.tags.filter((v) => v !== value) } };
    return state;
}
