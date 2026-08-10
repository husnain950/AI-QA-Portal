import { describe, expect, it } from 'vitest';
import {
    formatQualityFlagList,
    hasAnyQualityFlags,
    hasCriticalQualityFlags,
    normalizeQualityFlags,
} from '../utils/qualityFlags';

describe('qualityFlags', () => {
    it('normalizes string codes, objects, and JSON strings', () => {
        expect(normalizeQualityFlags(['missing_table', 'footnote_glue'])).toEqual([
            {
                code: 'missing_table',
                reason: 'Mentions a table but HTML has no <table>',
            },
            {
                code: 'footnote_glue',
                reason:
                    'Footnote digits appear glued into words (no proper cite markers)',
            },
        ]);

        expect(
            normalizeQualityFlags([
                { code: 'wall_of_text', reason: 'Custom wall reason' },
                { code: 'heading_body_bleed', message: 'Custom bleed' },
            ]),
        ).toEqual([
            { code: 'wall_of_text', reason: 'Custom wall reason' },
            { code: 'heading_body_bleed', reason: 'Custom bleed' },
        ]);

        expect(
            normalizeQualityFlags(
                JSON.stringify([{ code: 'missing_table' }, 'footnote_glue']),
            ),
        ).toHaveLength(2);
    });

    it('hasCriticalQualityFlags mirrors backend CRITICAL_FLAGS only', () => {
        expect(hasCriticalQualityFlags(null)).toBe(false);
        expect(hasCriticalQualityFlags([])).toBe(false);
        expect(hasCriticalQualityFlags(['missing_table'])).toBe(true);
        expect(hasCriticalQualityFlags(['page_range_out_of_bounds'])).toBe(false);
        expect(formatQualityFlagList(['missing_table'])[0]).toMatch(/table/i);
    });

    it('hasAnyQualityFlags is true for any non-empty flag set', () => {
        expect(hasAnyQualityFlags(null)).toBe(false);
        expect(hasAnyQualityFlags(['page_range_out_of_bounds'])).toBe(true);
        expect(hasAnyQualityFlags(['missing_table'])).toBe(true);
    });
});
