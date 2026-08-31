/**
 * The client sanitizer enforces the backend's policy, not a narrower one of its own.
 *
 * Every assertion here is a construct the old client allowlist silently deleted from
 * real pipeline output.
 */
import { describe, expect, it } from 'vitest';

import policy from '../utils/sanitizerPolicy.json';
import { sanitizeLegalHtml } from '../utils/sanitizeHtml';

describe('the classes the backend deliberately keeps', () => {
    // 11,349 occurrences across the two corpora, each with a live stylesheet rule.
    const classes = ['fn-table', 'omitted-bracket', 'explanation', 'defn', 'formula',
        'frac', 'legend'];

    it.each(classes)('keeps .%s', (name) => {
        expect(policy.knownClasses).toContain(name);
        expect(sanitizeLegalHtml(`<div class="${name}">x</div>`)).toContain(name);
    });

    it('still drops a class nobody emits', () => {
        expect(sanitizeLegalHtml('<div class="totally-made-up">x</div>'))
            .not.toContain('totally-made-up');
    });
});

describe('footnote table column widths', () => {
    it('survives, because the width is data recovered from the PDF', () => {
        const out = sanitizeLegalHtml(
            '<div class="fn-table"><div style="flex: 0 0 33.3333%">Rate</div></div>',
        );
        expect(out).toContain('fn-table');
        expect(out).toContain('flex:0 0 33.3333%');
    });

    it('and nothing else in a style attribute does', () => {
        const out = sanitizeLegalHtml(
            '<div style="position:fixed;top:0;flex: 0 0 10%">x</div>',
        );
        expect(out).toContain('flex:0 0 10%');
        expect(out).not.toContain('position');
        expect(out).not.toContain('top');
    });

    it('drops a flex value that is not the audited shape', () => {
        expect(sanitizeLegalHtml('<div style="flex: 1 0 42px">x</div>'))
            .not.toContain('flex');
    });
});

describe('the dangerous shapes', () => {
    it.each([
        ['<script>alert(1)</script><p>body</p>', 'script'],
        ['<p onclick="alert(1)">body</p>', 'onclick'],
        ['<iframe src="http://evil"></iframe><p>body</p>', 'iframe'],
        ['<img src=x onerror=alert(1)><p>body</p>', 'onerror'],
        ['<a href="javascript:alert(1)">x</a>', 'javascript'],
    ])('strips %s', (input, forbidden) => {
        expect(sanitizeLegalHtml(input)).not.toContain(forbidden);
    });

    it('keeps the statutory text around them', () => {
        expect(sanitizeLegalHtml('<script>alert(1)</script><p>body</p>')).toContain('body');
    });
});

describe('cite linkage', () => {
    it('keeps data-ref, which is how a cite finds its footnote', () => {
        expect(policy.allowedAttrs).toContain('data-ref');
        expect(sanitizeLegalHtml('<sup class="cite" data-ref="12.3">1</sup>'))
            .toContain('data-ref="12.3"');
    });
});

describe('a cite resolves by its identifier, not by its rendered text', () => {
    const footnotes = [
        { id: 'a', ref: '42.1', marker: '1', text: 'first note on page 42' },
        { id: 'b', ref: '43.1', marker: '1', text: 'first note on page 43' },
    ];
    const cite = (attrs, text) => {
        const el = document.createElement('sup');
        Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
        el.textContent = text;
        return el;
    };

    it('uses data-ref when the pipeline supplied one', async () => {
        const { findFootnoteForCite } = await import('../utils/footnoteCite');
        // Both footnotes render as marker "1". By text alone this is always the
        // first one; by identifier it is the right one.
        expect(findFootnoteForCite(cite({ 'data-ref': '43.1' }, '1'), footnotes).id)
            .toBe('b');
    });

    it('still resolves by text for a document that has no data-ref', async () => {
        const { findFootnoteForCite } = await import('../utils/footnoteCite');
        expect(findFootnoteForCite(cite({}, '1'), footnotes).id).toBe('a');
    });
});
