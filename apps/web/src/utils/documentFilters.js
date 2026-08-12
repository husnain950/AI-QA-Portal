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

const DEFAULT_FACETS = {
    corpusLane: '',
    sourceKind: '',
    health: '',
    review: '',
};

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

function completionPercent(doc) {
    const total = doc.total_sections || 0;
    if (total <= 0) return 0;
    return (doc.stats?.reviewed || 0) / total;
}

function healthSortKey(doc) {
    const facet = healthFacet(doc.health);
    if (facet === 'outside_gate') return 0;
    if (facet === 'within_gate') return 1;
    return 2;
}

function sortDocuments(documents, sort) {
    const list = [...documents];
    let result;
    switch (sort) {
        case 'newest':
            result = list.sort((a, b) => String(b.uploaded_at || '').localeCompare(String(a.uploaded_at || '')));
            break;
        case 'pages':
            result = list.sort((a, b) => (b.total_pages || 0) - (a.total_pages || 0)
                || a.name.localeCompare(b.name));
            break;
        case 'health':
            result = list.sort((a, b) => healthSortKey(a) - healthSortKey(b)
                || a.name.localeCompare(b.name));
            break;
        case 'completion':
            result = list.sort((a, b) => completionPercent(b) - completionPercent(a)
                || a.name.localeCompare(b.name));
            break;
        case 'name':
        default:
            result = list.sort((a, b) => a.name.localeCompare(b.name));
    }
    return result;
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
    let sort = 'name';

    if (typeof queryOrOptions === 'string' || queryOrOptions == null) {
        query = String(queryOrOptions || '');
        if (legacySourceFilter === 'acts_corpus') {
            facets.corpusLane = '';
            // Keep all non-manual corpus docs when legacy ACT Corpus selected.
            return sortDocuments(
                documents.filter((document) => {
                    const queryMatches = !query.trim()
                        || document.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
                    return queryMatches && document.source_type === 'acts_corpus';
                }),
                sort,
            );
        }
        if (legacySourceFilter === 'upload') {
            facets.corpusLane = 'manual';
        }
    } else {
        query = queryOrOptions.query || '';
        facets = { ...DEFAULT_FACETS, ...(queryOrOptions.facets || {}) };
        sort = queryOrOptions.sort || 'name';
    }

    const normalizedQuery = query.trim().toLocaleLowerCase();
    const filtered = documents.filter((document) => {
        const queryMatches = !normalizedQuery
            || document.name.toLocaleLowerCase().includes(normalizedQuery);
        return queryMatches
            && matchesLane(document, facets.corpusLane)
            && matchesSourceKind(document, facets.sourceKind)
            && matchesHealth(document, facets.health)
            && matchesReview(document, facets.review);
    });

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
 * preserved across and within groups for non-name sorts. Name sort keeps the
 * friendlier year-within-family ordering.
 *
 * @returns {{ familyKey: string, title: string, editions: Array, outsideGate: boolean }[]}
 */
export function groupDocumentsByFamily(documents, sort = 'name') {
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
    for (const [familyKey, docs] of map.entries()) {
        const editions = sort === 'name'
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
                (sort === 'name' ? editions[editions.length - 1] : editions[0])?.name || '',
            ).label,
            _order: Math.min(...docs.map((doc) => orderIndex.get(doc.id) ?? 0)),
        });
    }

    const sorted = sort === 'name'
        ? groups.sort((a, b) => a.title.localeCompare(b.title))
        : groups.sort((a, b) => a._order - b._order);

    return sorted.map(({ _order, ...group }) => group);
}
