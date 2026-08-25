import {
    editionDateFromName,
    familyKeyFromName,
    familyTitleFromKey,
    sortEditions,
} from './editions';
import { documentLane } from './corpusLanes';
import {
    healthFacet,
    reviewFacet,
} from './documentTags';

/**
 * @typedef {object} DocumentFacets
 * @property {string} [corpusLane]  lane id or ''
 * @property {string} [sourceKind]  native-digital | scanned-ocr | mixed-ocr | ''
 * @property {string} [health]      within_gate | outside_gate | unmeasured | ''
 * @property {string} [review]      complete | in_progress | untouched | ''
 */

export const DEFAULT_SORT = 'name';

/** Named sort menu. Separators are for the dropdown only. */
export const SORT_OPTIONS = [
    { value: 'name', label: 'Name — A → Z' },
    { value: 'name_desc', label: 'Name — Z → A' },
    { type: 'separator' },
    { value: 'newest', label: 'Recently added' },
    { value: 'oldest', label: 'Oldest added' },
    { value: 'year', label: 'Edition — newest' },
    { value: 'year_asc', label: 'Edition — oldest' },
    { type: 'separator' },
    { value: 'pages', label: 'Pages — largest' },
    { value: 'pages_asc', label: 'Pages — smallest' },
    { value: 'sections', label: 'Sections — largest' },
    { value: 'sections_asc', label: 'Sections — smallest' },
    { type: 'separator' },
    { value: 'completion', label: 'Review progress' },
    { value: 'flagged', label: 'Flagged sections' },
    { value: 'health', label: 'Health' },
];

export const SORT_VALUES = new Set(
    SORT_OPTIONS.filter((option) => option.value).map((option) => option.value),
);

export function sortLabel(sort) {
    return SORT_OPTIONS.find((option) => option.value === sort)?.label || SORT_OPTIONS[0].label;
}

export function isNameSort(sort) {
    return sort === 'name' || sort === 'name_desc';
}

const DEFAULT_FACETS = {
    corpusLane: '',
    sourceKind: '',
    health: '',
    review: '',
    flagged: '',
};

function matchesFlagged(document, flagged) {
    if (!flagged) return true;
    return (document.stats?.has_issues || 0) > 0;
}

function matchesLane(document, corpusLane) {
    if (!corpusLane) return true;
    return documentLane(document) === corpusLane;
}

function matchesSourceKind(document, sourceKind) {
    if (!sourceKind) return true;
    return document.provenance?.source_kind === sourceKind;
}

function matchesHealth(document, health) {
    if (!health) return true;
    return healthFacet(document.health) === health;
}

function matchesReview(document, review) {
    if (!review) return true;
    return reviewFacet(document) === review;
}

export function documentMatchesQuery(document, query) {
    const normalized = String(query || '').trim().toLocaleLowerCase();
    if (!normalized) return true;
    const family = familyTitleFromKey(familyKeyFromName(document.name || ''));
    const haystack = [document.name, document.pdf_filename, family]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase();
    return haystack.includes(normalized);
}

function completionPercent(doc) {
    const total = doc.total_sections || 0;
    if (total <= 0) return 0;
    return (doc.stats?.reviewed || 0) / total;
}

function flaggedCount(doc) {
    return doc.stats?.has_issues || 0;
}

function healthSortKey(doc) {
    const facet = healthFacet(doc.health);
    if (facet === 'outside_gate') return 0;
    if (facet === 'within_gate') return 1;
    return 2;
}

function byName(a, b) {
    return String(a.name || '').localeCompare(String(b.name || ''));
}

function byUploaded(a, b, desc) {
    const left = String(a.uploaded_at || '');
    const right = String(b.uploaded_at || '');
    const cmp = desc ? right.localeCompare(left) : left.localeCompare(right);
    return cmp || byName(a, b);
}

function byEditionYear(a, b, desc) {
    const da = editionDateFromName(a.name || '');
    const db = editionDateFromName(b.name || '');
    if (da.unknown && db.unknown) return byName(a, b);
    if (da.unknown) return 1;
    if (db.unknown) return -1;
    const diff = desc ? db.year - da.year : da.year - db.year;
    return diff || byName(a, b);
}

function sortDocuments(documents, sort) {
    const list = [...documents];
    switch (sort) {
        case 'name_desc':
            return list.sort((a, b) => byName(b, a));
        case 'newest':
            return list.sort((a, b) => byUploaded(a, b, true));
        case 'oldest':
            return list.sort((a, b) => byUploaded(a, b, false));
        case 'year':
            return list.sort((a, b) => byEditionYear(a, b, true));
        case 'year_asc':
            return list.sort((a, b) => byEditionYear(a, b, false));
        case 'pages':
            return list.sort((a, b) => (b.total_pages || 0) - (a.total_pages || 0) || byName(a, b));
        case 'pages_asc':
            return list.sort((a, b) => (a.total_pages || 0) - (b.total_pages || 0) || byName(a, b));
        case 'sections':
            return list.sort((a, b) => (b.total_sections || 0) - (a.total_sections || 0) || byName(a, b));
        case 'sections_asc':
            return list.sort((a, b) => (a.total_sections || 0) - (b.total_sections || 0) || byName(a, b));
        case 'health':
            return list.sort((a, b) => healthSortKey(a) - healthSortKey(b) || byName(a, b));
        case 'completion':
            return list.sort((a, b) => completionPercent(b) - completionPercent(a) || byName(a, b));
        case 'flagged':
            return list.sort((a, b) => flaggedCount(b) - flaggedCount(a) || byName(a, b));
        case 'name':
        default:
            return list.sort(byName);
    }
}

/**
 * Faceted Library filter.
 *
 * Legacy call shape `filterDocuments(docs, query, sourceFilter)` maps
 * acts_corpus/upload onto approximate lane filters for old tests.
 */
export const filterDocuments = (documents, queryOrOptions, legacySourceFilter) => {
    let query = '';
    let facets = { ...DEFAULT_FACETS };
    let sort = DEFAULT_SORT;

    if (typeof queryOrOptions === 'string' || queryOrOptions == null) {
        query = String(queryOrOptions || '');
        if (legacySourceFilter === 'acts_corpus') {
            facets.corpusLane = '';
            // Keep all non-manual corpus docs when legacy ACT Corpus selected.
            return sortDocuments(
                documents.filter((document) => (
                    documentMatchesQuery(document, query)
                    && document.source_type === 'acts_corpus'
                )),
                sort,
            );
        }
        if (legacySourceFilter === 'upload') {
            facets.corpusLane = 'manual';
        }
    } else {
        query = queryOrOptions.query || '';
        facets = { ...DEFAULT_FACETS, ...(queryOrOptions.facets || {}) };
        sort = queryOrOptions.sort || DEFAULT_SORT;
    }

    const filtered = documents.filter((document) => (
        documentMatchesQuery(document, query)
        && matchesLane(document, facets.corpusLane)
        && matchesSourceKind(document, facets.sourceKind)
        && matchesHealth(document, facets.health)
        && matchesReview(document, facets.review)
        && matchesFlagged(document, facets.flagged)
    ));

    return sortDocuments(filtered, sort);
};

/** Count documents per facet dimension (from the full library, not filtered). */
export function facetCounts(documents) {
    const lanes = {};
    const kinds = {};
    const health = {};
    const review = {};
    for (const doc of documents) {
        const lane = documentLane(doc);
        lanes[lane] = (lanes[lane] || 0) + 1;
        const kind = doc.provenance?.source_kind || 'unknown';
        kinds[kind] = (kinds[kind] || 0) + 1;
        const h = healthFacet(doc.health);
        health[h] = (health[h] || 0) + 1;
        const r = reviewFacet(doc);
        review[r] = (review[r] || 0) + 1;
    }
    return { lanes, kinds, health, review, total: documents.length };
}

/**
 * Group filtered documents by statute family.
 * ``documents`` should already be sorted by ``filterDocuments``; that order is
 * preserved across and within groups for non-name sorts. Name sorts keep the
 * friendlier year-within-family ordering (Z→A only reverses family titles).
 *
 * @returns {{ familyKey: string, title: string, editions: Array, outsideGate: boolean }[]}
 */
export function groupDocumentsByFamily(documents, sort = DEFAULT_SORT) {
    const orderIndex = new Map(documents.map((doc, index) => [doc.id, index]));
    const map = new Map();
    for (const doc of documents) {
        const key = familyKeyFromName(doc.name);
        if (!map.has(key)) {
            map.set(key, []);
        }
        map.get(key).push(doc);
    }
    const groups = [];
    const nameSort = isNameSort(sort);
    for (const [familyKey, docs] of map.entries()) {
        const editions = nameSort
            ? sortEditions(docs)
            : [...docs].sort(
                (a, b) => (orderIndex.get(a.id) ?? 0) - (orderIndex.get(b.id) ?? 0),
            );
        const outsideGate = editions.some((doc) => healthFacet(doc.health) === 'outside_gate');
        groups.push({
            familyKey,
            title: familyTitleFromKey(familyKey),
            editions,
            outsideGate,
            latestYear: editionDateFromName(
                (nameSort ? editions[editions.length - 1] : editions[0])?.name || '',
            ).label,
            _order: Math.min(...docs.map((doc) => orderIndex.get(doc.id) ?? 0)),
        });
    }

    const sorted = nameSort
        ? groups.sort((a, b) => {
            const cmp = a.title.localeCompare(b.title);
            return sort === 'name_desc' ? -cmp : cmp;
        })
        : groups.sort((a, b) => a._order - b._order);

    return sorted.map(({ _order, ...group }) => group);
}
