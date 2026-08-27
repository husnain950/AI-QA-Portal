/** Shared vocabulary for the server-driven Library: sort menu, facet labels,
 * view definitions, and the translation from URL state to v2 API parameters.
 *
 * Every value here must have a server counterpart in
 * apps/api/backend/services/library_query.py — the page never filters locally.
 */
import { isoDateDaysAgo } from './time';

export const DEFAULT_SORT = 'name';

/** Grouped sort menu. `relevance` is offered only while a search is active. */
export const SORT_GROUPS = [
    {
        label: null,
        options: [{ value: 'relevance', label: 'Most relevant', searchOnly: true }],
    },
    {
        label: 'Name',
        options: [
            { value: 'name', label: 'Title A → Z' },
            { value: 'name_desc', label: 'Title Z → A' },
        ],
    },
    {
        label: 'Dates',
        options: [
            { value: 'newest', label: 'Recently added' },
            { value: 'oldest', label: 'Oldest added' },
            { value: 'updated', label: 'Recently updated' },
            { value: 'year', label: 'Edition — newest first' },
            { value: 'year_asc', label: 'Edition — oldest first' },
        ],
    },
    {
        label: 'Size',
        options: [
            { value: 'pages', label: 'Pages — most first' },
            { value: 'pages_asc', label: 'Pages — fewest first' },
            { value: 'sections', label: 'Sections — most first' },
            { value: 'sections_asc', label: 'Sections — fewest first' },
        ],
    },
    {
        label: 'Review',
        options: [
            { value: 'completion', label: 'Review progress' },
            { value: 'flagged', label: 'Most flagged' },
            { value: 'health', label: 'Health — outside gate first' },
        ],
    },
];

export const SORT_OPTIONS = SORT_GROUPS.flatMap((group) => group.options);
export const SORT_VALUES = new Set(SORT_OPTIONS.map((option) => option.value));

export function sortLabel(sort, { searching = false } = {}) {
    if (sort === 'relevance' && !searching) return sortLabel(DEFAULT_SORT);
    return SORT_OPTIONS.find((option) => option.value === sort)?.label || 'Title A → Z';
}

export const VIEWS = [
    { value: 'all', label: 'All documents' },
    { value: 'favorites', label: 'Favorites' },
    { value: 'recent', label: 'Recently viewed' },
];
export const VIEW_VALUES = new Set(VIEWS.map((view) => view.value));

export const KIND_LABELS = {
    'native-digital': 'Native digital',
    'scanned-ocr': 'Scanned (OCR)',
    'mixed-ocr': 'Mixed OCR',
    unknown: 'Unknown',
};

export const HEALTH_LABELS = {
    within_gate: 'Within gate',
    outside_gate: 'Outside gate',
    unmeasured: 'Unmeasured',
};

export const REVIEW_LABELS = {
    complete: 'Complete',
    in_progress: 'In progress',
    untouched: 'Untouched',
};

export const TAG_LABELS = {
    'native-digital': 'Native digital',
    'scanned-ocr': 'Scanned (OCR)',
    'mixed-ocr': 'Mixed OCR',
    'ocr-provisional': 'OCR provisional',
    'ocr-needs-review': 'OCR needs review',
    'pdf-inferred': 'Inferred from PDF',
};

export const ADDED_PRESETS = [
    { value: '7d', label: 'Last 7 days', days: 7 },
    { value: '30d', label: 'Last 30 days', days: 30 },
    { value: '90d', label: 'Last 90 days', days: 90 },
];

export const PAGE_PRESETS = [
    { value: 'small', label: 'Under 50 pages', min: null, max: 49 },
    { value: 'medium', label: '50 – 200 pages', min: 50, max: 200 },
    { value: 'large', label: '200 – 1000 pages', min: 200, max: 1000 },
    { value: 'huge', label: 'Over 1000 pages', min: 1001, max: null },
];

export function pagePresetFor(min, max) {
    return PAGE_PRESETS.find(
        (preset) => preset.min === (min ?? null) && preset.max === (max ?? null),
    )?.value || '';
}

export function tagLabel(tag) {
    return TAG_LABELS[tag] || tag;
}

/**
 * Translate library state to v2 API params. Returns `{ page, facets }` URLSearchParams
 * pair; `page` is null when a client-side view (favorites/recents) is empty — the
 * caller must render an empty result without a request. The facets params carry
 * `ids=-` in that case so counts collapse to zero while library-wide totals still
 * come back for the header strip.
 */
export function buildApiParams(state, { favoriteIds = [], recentIds = [] } = {}) {
    const { query, sort, view, facets } = state;
    const params = new URLSearchParams();
    const q = String(query || '').trim();
    if (q) params.set('q', q);
    if (facets.lanes.length) params.set('lane', facets.lanes.join(','));
    if (facets.kinds.length) params.set('kind', facets.kinds.join(','));
    if (facets.health.length) params.set('health', facets.health.join(','));
    if (facets.review.length) params.set('review', facets.review.join(','));
    if (facets.flagged) params.set('flagged', '1');
    if (facets.annotations) params.set('annotations', '1');
    if (facets.years.length) params.set('year', facets.years.join(','));
    if (facets.yearFrom != null) params.set('year_from', String(facets.yearFrom));
    if (facets.yearTo != null) params.set('year_to', String(facets.yearTo));
    const addedAfter = facets.addedPreset
        ? isoDateDaysAgo(ADDED_PRESETS.find((preset) => preset.value === facets.addedPreset)?.days || 0)
        : facets.addedAfter;
    if (addedAfter) params.set('added_after', addedAfter);
    if (facets.addedBefore) params.set('added_before', facets.addedBefore);
    if (facets.pagesMin != null) params.set('pages_min', String(facets.pagesMin));
    if (facets.pagesMax != null) params.set('pages_max', String(facets.pagesMax));
    if (facets.tags.length) params.set('tag', facets.tags.join(','));

    const effectiveSort = sort === 'relevance' && !q ? DEFAULT_SORT : sort;
    if (effectiveSort && effectiveSort !== DEFAULT_SORT) params.set('sort', effectiveSort);

    let pageParams = params;
    if (view === 'favorites' || view === 'recent') {
        const ids = (view === 'favorites' ? favoriteIds : recentIds).slice(0, 500);
        const facetsParams = new URLSearchParams(params);
        facetsParams.set('ids', ids.length ? ids.join(',') : '-');
        if (!ids.length) return { page: null, facets: facetsParams };
        pageParams = new URLSearchParams(params);
        pageParams.set('ids', ids.join(','));
        return { page: pageParams, facets: facetsParams };
    }
    return { page: pageParams, facets: params };
}

/** Number of active filter dimensions — the badge on the Filters button. */
export function countActiveFilters(facets) {
    return (
        facets.lanes.length
        + facets.kinds.length
        + facets.health.length
        + facets.review.length
        + (facets.flagged ? 1 : 0)
        + (facets.annotations ? 1 : 0)
        + (facets.years.length || facets.yearFrom != null || facets.yearTo != null ? 1 : 0)
        + (facets.addedPreset || facets.addedAfter || facets.addedBefore ? 1 : 0)
        + (facets.pagesMin != null || facets.pagesMax != null ? 1 : 0)
        + facets.tags.length
    );
}

export function docCompletion(doc) {
    const total = doc.total_sections || 0;
    if (total <= 0) return 0;
    return Math.round(((doc.stats?.reviewed || 0) / total) * 100);
}
