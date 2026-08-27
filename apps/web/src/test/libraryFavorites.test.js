import { beforeEach, describe, expect, it } from 'vitest';
import { useFavorites } from '../utils/favorites';
import { recordDocumentView, useRecents } from '../utils/recents';
import { buildApiParams, countActiveFilters } from '../utils/libraryQuery';
import { EMPTY_FACETS } from '../utils/libraryState';

const STATE = {
    query: '',
    sort: 'name',
    view: 'all',
    group: true,
    facets: { ...EMPTY_FACETS },
};

describe('favorites', () => {
    beforeEach(() => {
        window.localStorage.clear();
        useFavorites.setState({ ids: [] });
    });

    it('toggles and persists', () => {
        useFavorites.getState().toggle('doc-1');
        useFavorites.getState().toggle('doc-2');
        expect(useFavorites.getState().ids).toEqual(['doc-2', 'doc-1']);
        expect(JSON.parse(window.localStorage.getItem('qa-portal-library-favorites'))).toEqual(['doc-2', 'doc-1']);

        useFavorites.getState().toggle('doc-1');
        expect(useFavorites.getState().ids).toEqual(['doc-2']);
    });

    it('addMany dedupes and fronts new ids', () => {
        useFavorites.getState().toggle('doc-1');
        useFavorites.getState().addMany(['doc-1', 'doc-3']);
        expect(useFavorites.getState().ids).toEqual(['doc-3', 'doc-1']);
    });
});

describe('recents', () => {
    beforeEach(() => {
        window.localStorage.clear();
        useRecents.setState({ ids: [] });
    });

    it('records newest-first without duplicates', () => {
        recordDocumentView('a');
        recordDocumentView('b');
        recordDocumentView('a');
        expect(useRecents.getState().ids).toEqual(['a', 'b']);
    });

    it('caps the list at 50', () => {
        for (let index = 0; index < 60; index += 1) recordDocumentView(`doc-${index}`);
        expect(useRecents.getState().ids).toHaveLength(50);
        expect(useRecents.getState().ids[0]).toBe('doc-59');
    });
});

describe('buildApiParams', () => {
    it('maps state to v2 query params and omits the default sort', () => {
        const { page, facets } = buildApiParams({
            ...STATE,
            query: 'tax',
            sort: 'newest',
            facets: {
                ...EMPTY_FACETS,
                lanes: ['customs'],
                kinds: ['scanned-ocr', 'unknown'],
                flagged: true,
                years: [1969],
                pagesMin: 50,
                addedPreset: '7d',
                tags: ['ocr-provisional'],
            },
        });
        expect(page.get('q')).toBe('tax');
        expect(page.get('lane')).toBe('customs');
        expect(page.get('kind')).toBe('scanned-ocr,unknown');
        expect(page.get('flagged')).toBe('1');
        expect(page.get('year')).toBe('1969');
        expect(page.get('pages_min')).toBe('50');
        expect(page.get('added_after')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(page.get('tag')).toBe('ocr-provisional');
        expect(page.get('sort')).toBe('newest');
        expect(facets.get('q')).toBe('tax');
    });

    it('passes favorite ids server-side and degrades empty views without a page request', () => {
        const empty = buildApiParams({ ...STATE, view: 'favorites' }, { favoriteIds: [] });
        expect(empty.page).toBeNull();
        expect(empty.facets.get('ids')).toBe('-');

        const filled = buildApiParams({ ...STATE, view: 'favorites' }, { favoriteIds: ['a', 'b'] });
        expect(filled.page.get('ids')).toBe('a,b');
    });

    it('drops a dangling relevance sort when the search box is empty', () => {
        const { page } = buildApiParams({ ...STATE, sort: 'relevance' });
        expect(page.get('sort')).toBeNull();
        const searching = buildApiParams({ ...STATE, query: 'tax', sort: 'relevance' });
        expect(searching.page.get('sort')).toBe('relevance');
    });
});

describe('countActiveFilters', () => {
    it('counts selections in list facets and one per range/flag', () => {
        expect(countActiveFilters({ ...EMPTY_FACETS })).toBe(0);
        expect(countActiveFilters({
            ...EMPTY_FACETS,
            lanes: ['customs', 'manual'],
            flagged: true,
            pagesMin: 10,
            pagesMax: 100,
            years: [1969],
        })).toBe(5);
    });
});
