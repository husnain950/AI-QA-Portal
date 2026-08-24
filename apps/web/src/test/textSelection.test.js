import { describe, expect, it } from 'vitest';

import { highlightFromOffsets } from '../hooks/useTextSelection';

describe('highlightFromOffsets', () => {
    it('emits highlighted_text equal to textContent.slice(start, end)', () => {
        const element = document.createElement('div');
        element.innerHTML = '<p>includes<sup class="cite">2.4</sup> any other officers</p>';
        const full = element.textContent;
        const start = full.indexOf('any other officers');
        const end = start + 'any other officers'.length;
        const highlight = highlightFromOffsets(element, start, end);

        expect(highlight.text).toBe('any other officers');
        expect(highlight.text).toBe(full.slice(highlight.start, highlight.end));
        expect(highlight.start).toBe(start);
        expect(highlight.end).toBe(end);
    });

    it('shrinks offsets inward when the range has surrounding whitespace', () => {
        const element = document.createElement('div');
        element.textContent = 'alpha  bravo  charlie';
        const full = element.textContent;
        const paddedStart = full.indexOf('bravo') - 1;
        const paddedEnd = full.indexOf('bravo') + 'bravo'.length + 1;
        expect(full.slice(paddedStart, paddedEnd)).toBe(' bravo ');

        const highlight = highlightFromOffsets(element, paddedStart, paddedEnd);
        expect(highlight.text).toBe('bravo');
        expect(highlight.text).toBe(full.slice(highlight.start, highlight.end));
        expect(highlight.start).toBe(paddedStart + 1);
        expect(highlight.end).toBe(paddedEnd - 1);
    });

    it('returns null when the range is only whitespace', () => {
        const element = document.createElement('div');
        element.textContent = 'alpha   bravo';
        expect(highlightFromOffsets(element, 5, 8)).toBeNull();
    });
});
