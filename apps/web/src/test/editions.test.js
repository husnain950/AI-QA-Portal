import { describe, expect, it } from 'vitest';
import {
    editionDateFromName,
    familyKeyFromName,
    sortEditions,
} from '../utils/editions';

describe('editions', () => {
    it('derives family keys without edition noise', () => {
        expect(
            familyKeyFromName('Customs Act, 1969 as amended up to 30.06.2025'),
        ).toMatch(/customs act/i);
        expect(
            familyKeyFromName('Customs Act ,1969 (Amended upto 30th June 2007)'),
        ).toMatch(/customs act/i);
    });

    it('parses edition years and falls back visibly', () => {
        expect(editionDateFromName('… up to 30.06.2025').year).toBe(2025);
        expect(editionDateFromName('Income Tax Ordinance 2011-12').year).toBe(2011);
        const unk = editionDateFromName('Mystery Gazette Without Year');
        expect(unk.unknown).toBe(true);
        expect(unk.label).toBe('year unknown');
        expect(unk.sortKey).toBe(9999);
    });

    it('sorts unknown years last', () => {
        const sorted = sortEditions([
            { name: 'Act 2020' },
            { name: 'Mystery' },
            { name: 'Act 2018' },
        ]);
        expect(sorted.map((d) => d.name)).toEqual(['Act 2018', 'Act 2020', 'Mystery']);
    });
});
