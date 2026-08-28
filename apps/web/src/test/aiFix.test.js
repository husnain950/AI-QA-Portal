import { describe, expect, it } from 'vitest';
import {
    changeSummary,
    classifyDiffLine,
    formatModelPricing,
    hasApprovedFix,
    htmlChangeHints,
    normalizeModelList,
    pagesSentToModel,
    panelFootnotes,
    seedInstructions,
    validationSummary,
} from '../utils/aiFix';

describe('pagesSentToModel', () => {
    it('returns the inclusive 1-based span, capped at 4', () => {
        expect(pagesSentToModel(82, 83)).toEqual([82, 83]);
        expect(pagesSentToModel(10, 20)).toEqual([10, 11, 12, 13]);
        expect(pagesSentToModel(5, 5)).toEqual([5]);
    });

    it('swaps an inverted range and defaults missing pages', () => {
        expect(pagesSentToModel(4, 2)).toEqual([2, 3, 4]);
        expect(pagesSentToModel(null, null)).toEqual([1]);
    });
});

describe('formatModelPricing', () => {
    it('formats input and output prices', () => {
        expect(formatModelPricing({
            input_price_per_1m: 3,
            output_price_per_1m: 15,
        })).toBe('$3 / 1M input · $15 / 1M output');
    });

    it('returns null when pricing is missing', () => {
        expect(formatModelPricing({})).toBeNull();
    });

    it('formats the dropdown pricing line', () => {
        expect(formatModelPricing({
            input_price_per_1m: 0.2,
            output_price_per_1m: 1.25,
        })).toBe('$0.2 / 1M input · $1.25 / 1M output');
    });
});

describe('normalizeModelList', () => {
    it('accepts rich model objects from the API', () => {
        expect(normalizeModelList({
            models: [{
                id: 'gpt-5.4',
                label: 'GPT 5.4',
                vision: true,
                input_price_per_1m: 2.5,
                output_price_per_1m: 15,
            }],
            default: 'gpt-5.4',
        })).toEqual([{
            id: 'gpt-5.4',
            label: 'GPT 5.4',
            vision: true,
            input_price_per_1m: 2.5,
            output_price_per_1m: 15,
        }]);
    });

    it('tolerates legacy string ids', () => {
        expect(normalizeModelList({ models: ['kimi'], default: 'kimi' })).toEqual([{
            id: 'kimi',
            label: 'kimi',
            vision: false,
            input_price_per_1m: null,
            output_price_per_1m: null,
        }]);
    });
});

describe('classifyDiffLine', () => {
    it('labels unified diff lines for styling', () => {
        expect(classifyDiffLine('@@ -1,3 +1,3 @@')).toBe('hunk');
        expect(classifyDiffLine('+added text')).toBe('add');
        expect(classifyDiffLine('-removed text')).toBe('del');
        expect(classifyDiffLine(' unchanged context')).toBe('ctx');
        expect(classifyDiffLine(undefined)).toBe('ctx');
    });
});

describe('validationSummary', () => {
    it('splits issues by level and blocks on errors', () => {
        const summary = validationSummary([
            { level: 'error', code: 'unsafe_html', message: 'active content' },
            { level: 'warning', code: 'no_change', message: 'nothing changed' },
        ]);
        expect(summary.errors).toEqual(['active content']);
        expect(summary.warnings).toEqual(['nothing changed']);
        expect(summary.blocked).toBe(true);
    });

    it('does not block on warnings alone', () => {
        const summary = validationSummary([
            { level: 'warning', code: 'no_change', message: 'nothing changed' },
        ]);
        expect(summary.blocked).toBe(false);
    });

    it('tolerates missing input', () => {
        expect(validationSummary(null)).toEqual({
            errors: [],
            warnings: [],
            blocked: false,
        });
    });
});

describe('seedInstructions', () => {
    it('builds a seed from open annotations only', () => {
        const seed = seedInstructions([
            {
                status: 'open',
                highlighted_text: 'sub-section (2)',
                issue_description: 'proviso is missing',
            },
            { status: 'resolved', highlighted_text: 'old', issue_description: 'done' },
            { status: 'open', highlighted_text: 'garbled run' },
        ]);
        expect(seed).toContain('"sub-section (2)": proviso is missing');
        expect(seed).toContain('"garbled run"');
        expect(seed).not.toContain('old');
    });

    it('returns an empty string with no open annotations', () => {
        expect(seedInstructions([])).toBe('');
        expect(seedInstructions(null)).toBe('');
    });
});

describe('changeSummary', () => {
    it('reports character and footnote deltas', () => {
        const lines = changeSummary({
            stats: {
                chars_before: 100,
                chars_after: 150,
                footnotes_before: 2,
                footnotes_after: 1,
            },
        });
        expect(lines).toContain('50 characters added');
        expect(lines).toContain('1 footnote removed');
    });

    it('notes wording-only changes', () => {
        const lines = changeSummary({
            stats: {
                chars_before: 100,
                chars_after: 100,
                footnotes_before: 0,
                footnotes_after: 0,
            },
            plain_text_diff: ['-old', '+new'],
        });
        expect(lines).toEqual(['wording changed with no net length change']);
    });

    it('is empty without stats', () => {
        expect(changeSummary(null)).toEqual([]);
    });
});

describe('htmlChangeHints', () => {
    it('reports span.proviso becoming p.proviso', () => {
        const hints = htmlChangeHints(
            '<span class="proviso">Provided</span>',
            '<p class="proviso">Provided</p>',
        );
        expect(hints).toContain('span.proviso -1');
        expect(hints).toContain('p.proviso +1');
    });

    it('is empty when markup is unchanged', () => {
        expect(htmlChangeHints('<p class="proviso">x</p>', '<p class="proviso">x</p>')).toEqual([]);
    });
});

describe('panelFootnotes', () => {
    it('accepts model-shaped footnotes and portal rows', () => {
        expect(panelFootnotes([
            { ref: '67.1', marker: '67.1', text: 'Finance Act', html: '<p>Finance Act</p>' },
            { id: 'db', marker: '2', text: 'note', html_content: '<p>note</p>', review_status: 'open' },
        ])).toEqual([
            {
                id: '67.1',
                marker: '67.1',
                page: null,
                text: 'Finance Act',
                html_content: '<p>Finance Act</p>',
                review_status: 'pending',
            },
            {
                id: 'db',
                marker: '2',
                page: null,
                text: 'note',
                html_content: '<p>note</p>',
                review_status: 'open',
            },
        ]);
    });
});

describe('hasApprovedFix', () => {
    it('is true only for an approved proposal on that section', () => {
        const proposals = [
            { section_id: 'a', status: 'rejected' },
            { section_id: 'a', status: 'approved' },
            { section_id: 'b', status: 'proposed' },
        ];
        expect(hasApprovedFix(proposals, 'a')).toBe(true);
        expect(hasApprovedFix(proposals, 'b')).toBe(false);
        expect(hasApprovedFix(null, 'a')).toBe(false);
    });
});
