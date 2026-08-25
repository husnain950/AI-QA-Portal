import { describe, expect, it } from 'vitest';
import {
    libraryFilterChips,
    parseLibrarySearchParams,
    serializeLibrarySearchParams,
} from '../utils/libraryState';

describe('library URL state', () => {
    it('round-trips filters and omits the default sort', () => {
        const params = serializeLibrarySearchParams({
            query: ' customs ',
            facets: {
                corpusLane: 'customs',
                sourceKind: 'scanned-ocr',
                health: '',
                review: 'untouched',
                flagged: 'flagged',
            },
            sort: 'name',
        });
        expect(params.toString()).toBe('q=customs&lane=customs&kind=scanned-ocr&review=untouched&flagged=1');
        expect(parseLibrarySearchParams(params)).toEqual({
            query: 'customs',
            sort: '',
            facets: {
                corpusLane: 'customs',
                sourceKind: 'scanned-ocr',
                health: '',
                review: 'untouched',
                flagged: 'flagged',
            },
        });
    });

    it('keeps a non-default sort and drops unknown values', () => {
        const params = new URLSearchParams('q=ito&kind=paper&sort=pages_asc&flagged=yes');
        expect(parseLibrarySearchParams(params)).toEqual({
            query: 'ito',
            sort: 'pages_asc',
            facets: {
                corpusLane: '',
                sourceKind: '',
                health: '',
                review: '',
                flagged: '',
            },
        });
    });

    it('builds removable chips for the active filters', () => {
        const chips = libraryFilterChips({
            query: 'income',
            facets: {
                corpusLane: 'ordinance',
                sourceKind: 'scanned-ocr',
                review: 'complete',
                flagged: 'flagged',
            },
        });
        expect(chips.map((chip) => chip.label)).toEqual([
            '“income”',
            'Source: Income Tax Ordinance',
            'Scanned',
            'Complete',
            'Flagged',
        ]);
    });
});
