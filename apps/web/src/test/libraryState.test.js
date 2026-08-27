import { describe, expect, it } from 'vitest';
import {
    EMPTY_FACETS,
    clearChip,
    hasActiveFilters,
    libraryFilterChips,
    parseLibrarySearchParams,
    serializeLibrarySearchParams,
} from '../utils/libraryState';

const ROUND_TRIP_STATE = {
    query: 'customs',
    sort: 'pages_asc',
    view: 'all',
    group: false,
    facets: {
        ...EMPTY_FACETS,
        lanes: ['customs', 'ordinance'],
        kinds: ['scanned-ocr'],
        review: ['untouched'],
        flagged: true,
        years: [1969, 2002],
        addedPreset: '30d',
        pagesMin: 50,
        pagesMax: 200,
        tags: ['ocr-needs-review'],
    },
};

describe('library URL state', () => {
    it('round-trips the full filter set', () => {
        const params = serializeLibrarySearchParams(ROUND_TRIP_STATE);
        expect(params.get('lane')).toBe('customs,ordinance');
        expect(params.get('flagged')).toBe('1');
        expect(params.get('year')).toBe('1969,2002');
        expect(params.get('group')).toBe('0');
        expect(parseLibrarySearchParams(params)).toEqual({
            query: 'customs',
            sort: 'pages_asc',
            view: 'all',
            group: false,
            facets: ROUND_TRIP_STATE.facets,
        });
    });

    it('omits defaults so a clean library has an empty query string', () => {
        const params = serializeLibrarySearchParams({
            query: '', facets: { ...EMPTY_FACETS }, sort: 'name', view: 'all', group: true,
        });
        expect(params.toString()).toBe('');
    });

    it('parses legacy single-value facets into arrays', () => {
        const parsed = parseLibrarySearchParams(
            new URLSearchParams('lane=customs&kind=scanned-ocr&health=within_gate&review=complete&flagged=1'),
        );
        expect(parsed.facets.lanes).toEqual(['customs']);
        expect(parsed.facets.kinds).toEqual(['scanned-ocr']);
        expect(parsed.facets.health).toEqual(['within_gate']);
        expect(parsed.facets.review).toEqual(['complete']);
        expect(parsed.facets.flagged).toBe(true);
    });

    it('drops unknown values rather than forwarding them to the API', () => {
        const parsed = parseLibrarySearchParams(
            new URLSearchParams('lane=atlantis&kind=paper&sort=sideways&view=mine&year=abcd&added=whenever'),
        );
        expect(parsed.facets.lanes).toEqual([]);
        expect(parsed.facets.kinds).toEqual([]);
        expect(parsed.sort).toBe('');
        expect(parsed.view).toBe('all');
        expect(parsed.facets.years).toEqual([]);
        expect(parsed.facets.addedPreset).toBe('');
    });

    it('builds a chip per active filter with removable keys', () => {
        const chips = libraryFilterChips({
            query: 'income',
            view: 'favorites',
            facets: {
                ...EMPTY_FACETS,
                lanes: ['ordinance'],
                kinds: ['scanned-ocr'],
                review: ['complete'],
                flagged: true,
                years: [1969],
                addedAfter: '2026-01-01',
            },
        });
        expect(chips.map((chip) => chip.key)).toEqual([
            'view', 'q', 'lane:ordinance', 'kind:scanned-ocr',
            'review:complete', 'flagged', 'year:1969', 'added',
        ]);
        expect(chips.map((chip) => chip.label)).toContain('Source: Income Tax Ordinance');
    });

    it('clearChip removes exactly one filter at a time', () => {
        const state = {
            query: 'q',
            sort: 'name',
            view: 'favorites',
            group: true,
            facets: { ...EMPTY_FACETS, lanes: ['customs', 'manual'], flagged: true },
        };
        expect(clearChip(state, 'view').view).toBe('all');
        expect(clearChip(state, 'q').query).toBe('');
        expect(clearChip(state, 'lane:customs').facets.lanes).toEqual(['manual']);
        expect(clearChip(state, 'flagged').facets.flagged).toBe(false);
        expect(state.facets.lanes).toEqual(['customs', 'manual'], 'clearChip does not mutate');
    });

    it('hasActiveFilters covers query, view, and every facet', () => {
        const base = { query: '', sort: 'name', view: 'all', facets: { ...EMPTY_FACETS } };
        expect(hasActiveFilters(base)).toBe(false);
        expect(hasActiveFilters({ ...base, query: 'x' })).toBe(true);
        expect(hasActiveFilters({ ...base, view: 'recent' })).toBe(true);
        expect(hasActiveFilters({ ...base, facets: { ...EMPTY_FACETS, pagesMax: 100 } })).toBe(true);
    });
});
