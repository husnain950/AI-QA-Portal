import { describe, expect, it } from 'vitest';

import { summarizeJsonStructure } from '../utils/jsonStructure';

const leaf = (code, text, footnotes = []) => ({
    code,
    html: `<p>${text}</p>`,
    plain_text: text,
    footnotes,
});

describe('upload JSON structure traversal', () => {
    it('counts chapters, schedules, and leaves inside multiple instruments', () => {
        const parsed = {
            metadata: { instruments_count: 2 },
            instruments: [
                {
                    code: 'SRO-ONE',
                    chapters: [{
                        code: 'CHAPTER I',
                        parts: [],
                        divisions: [],
                        sections: [leaf('1', 'First', [{ marker: '1' }])],
                    }],
                    schedules: [],
                },
                {
                    code: 'SRO-TWO',
                    chapters: [{
                        code: 'CHAPTER I',
                        parts: [{
                            code: 'PART I',
                            html: '<p>Continuation</p>',
                            plain_text: 'Continuation',
                            footnotes: [],
                        }],
                        divisions: [],
                        sections: [leaf('1', 'Second')],
                    }],
                    schedules: [{
                        code: 'FIRST SCHEDULE',
                        parts: [],
                        divisions: [],
                        sections: [leaf('A', 'Schedule entry')],
                    }],
                },
            ],
        };

        expect(summarizeJsonStructure(parsed)).toEqual({
            instrumentsCount: 2,
            chaptersCount: 2,
            schedulesCount: 1,
            sectionsCount: 4,
            sectionsWithHtml: 4,
            footnoteCount: 1,
        });
    });

    it('keeps the legacy top-level shape backward compatible', () => {
        expect(summarizeJsonStructure({
            chapters: [{
                sections: [leaf('1', 'Legacy')],
                parts: [],
                divisions: [],
            }],
            schedules: [],
        })).toMatchObject({
            instrumentsCount: 0,
            chaptersCount: 1,
            schedulesCount: 0,
            sectionsCount: 1,
        });
    });
});
