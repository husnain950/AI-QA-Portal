import { describe, expect, it } from 'vitest';
import {
    formatHierarchyLabel,
    formatLeafIdentity,
    formatLeafJsonPath,
    formatSectionLabel,
    leafHierarchyLines,
    resolveHierarchyKind,
} from '../utils/tocLabels';

describe('tocLabels', () => {
    it('skips empty hierarchy labels that would render as bare colon', () => {
        expect(formatHierarchyLabel('', '')).toBeNull();
        expect(formatHierarchyLabel(null, null)).toBeNull();
        expect(formatHierarchyLabel('CHAPTER I', 'PRELIMINARY')).toBe(
            'CHAPTER I: PRELIMINARY',
        );
        expect(formatHierarchyLabel('PART I', '')).toBe('PART I');
    });

    it('formats section labels without redundant Section prefix for containers', () => {
        expect(formatSectionLabel('1', 'Short title')).toBe('Section 1: Short title');
        expect(formatSectionLabel('PART I', '')).toBe('PART I');
        expect(formatSectionLabel('2', '')).toBe('Section 2');
        expect(formatSectionLabel('CHAPTER II', 'Appointments')).toBe(
            'CHAPTER II: Appointments',
        );
    });

    it('does not invent p.N labels for empty code and heading', () => {
        expect(formatSectionLabel('', '', 12)).toBeNull();
        expect(formatSectionLabel('', '')).toBeNull();
        expect(formatSectionLabel(null, null, 932)).toBeNull();
        expect(formatSectionLabel('  ', '  ', 1)).toBeNull();
        expect(formatLeafIdentity('', '')).toBe('Untitled leaf');
        expect(formatLeafIdentity('3', '')).toBe('Section 3');
    });

    it('resolves schedule kind from hierarchy_kind or schedule text', () => {
        expect(resolveHierarchyKind('schedule', 'I', 'Rates')).toBe('schedule');
        expect(resolveHierarchyKind('chapter', 'I', 'Rates')).toBe('chapter');
        expect(resolveHierarchyKind(null, 'THE FIRST SCHEDULE', '')).toBe('schedule');
        expect(resolveHierarchyKind(null, 'I', 'SECOND SCHEDULE')).toBe('schedule');
        expect(formatHierarchyLabel('I', 'Rates', 'schedule')).toBe('Schedule I: Rates');
        expect(formatHierarchyLabel('THE FIRST SCHEDULE', 'Rates', 'schedule')).toBe(
            'THE FIRST SCHEDULE: Rates',
        );
    });

    // `cleanHeading` lived here and re-ran json_parser.normalize_heading's regex set
    // on a string the backend had already cleaned at ingest -- the last of P6's six
    // client forks.  It also carried the backend's own bug: the dot-leader pattern
    // ate the `[...]` omission marker.  The API is the one normaliser now, so what
    // this module owes is to render what it is given.
    it('renders the API heading verbatim, including the omission marker', () => {
        expect(formatSectionLabel('30A', 'Directorate General [...] Internal Audit'))
            .toBe('Section 30A: Directorate General [...] Internal Audit');
        expect(formatHierarchyLabel('CHAPTER I', 'Definitions [...] and scope'))
            .toBe('CHAPTER I: Definitions [...] and scope');
        expect(
            leafHierarchyLines({ section_code: '7', section_heading: '[ ... ] Return' }),
        ).toEqual(['Section 7 · [ ... ] Return']);
    });

    it('still trims whitespace and skips blank headings', () => {
        expect(formatSectionLabel('1', '  Short title  ')).toBe('Section 1: Short title');
        expect(formatSectionLabel('2', '   ')).toBe('Section 2');
    });
});

describe('container codes are not prefixed with "Section "', () => {
    // 5,393 leaves in the corpus rendered as "Section THE FIRST SCHEDULE" / "Section
    // Annex-B" / "Section Contents" because the container test only matched the first
    // word, and the corpus never prints a schedule that way.
    it.each([
        ['THE FIRST SCHEDULE', 'RATES'],
        ['SIXTH SCHEDULE', 'Table-1'],
        ['FIFTH SCHEDULE', ''],
        ['Annex-B', 'CERTIFICATE'],
        ['ANNEXURE', ''],
        ['Contents', 'Contents · p3'],
        ['SECTION II', 'VEGETABLE PRODUCTS'],
        ['PART I', 'PRELIMINARY'],
        ['CHAPTER X', 'PROCEDURE'],
    ])('%s is a container', (code, heading) => {
        expect(formatSectionLabel(code, heading)).not.toMatch(/^Section /);
    });

    it('still labels a real section number', () => {
        expect(formatSectionLabel('113', 'Minimum tax')).toBe('Section 113: Minimum tax');
        expect(formatSectionLabel('7A', '')).toBe('Section 7A');
    });
});

describe('leaf JSON path locator', () => {
    const customsLeaf = {
        chapter_code: 'V',
        chapter_heading: 'LEVY OF, EXEMPTION FROM, AND REPAYMENT OF, CUSTOMS-DUTIES',
        hierarchy_kind: 'chapter',
        section_code: '25C',
        section_heading: 'Power to takeover the imported goods',
        source_key: '/chapters/4/sections/2',
    };

    it('formats chapter and section lines like breadcrumb chrome', () => {
        expect(leafHierarchyLines(customsLeaf)).toEqual([
            'Chapter V · LEVY OF, EXEMPTION FROM, AND REPAYMENT OF, CUSTOMS-DUTIES',
            'Section 25C · Power to takeover the imported goods',
        ]);
    });

    it('includes part and division when present', () => {
        expect(leafHierarchyLines({
            chapter_code: 'I',
            chapter_heading: 'PRELIMINARY',
            part_code: 'II',
            part_heading: 'Definitions',
            division_code: 'A',
            division_heading: 'General',
            section_code: '2',
            section_heading: 'Interpretation',
        })).toEqual([
            'Chapter I · PRELIMINARY',
            'Part II · Definitions',
            'Division A · General',
            'Section 2 · Interpretation',
        ]);
    });

    it('labels schedule containers as Schedule', () => {
        expect(leafHierarchyLines({
            chapter_code: 'I',
            chapter_heading: 'RATES',
            hierarchy_kind: 'schedule',
            section_code: '1',
            section_heading: 'Rate of tax',
        })).toEqual([
            'Schedule I · RATES',
            'Section 1 · Rate of tax',
        ]);
    });

    it('builds a paste-ready locator with document, leaf index, and JSON pointer', () => {
        expect(formatLeafJsonPath({
            documentName: 'Customs Act, 1969 as amended up to 30th June, 2025',
            section: customsLeaf,
            leafIndex: 60,
            leafCount: 331,
        })).toBe(
            [
                'Customs Act, 1969 as amended up to 30th June, 2025',
                'Chapter V · LEVY OF, EXEMPTION FROM, AND REPAYMENT OF, CUSTOMS-DUTIES',
                'Section 25C · Power to takeover the imported goods',
                'Leaf 60 of 331',
                '/chapters/4/sections/2',
            ].join('\n'),
        );
    });

    it('omits source_key when missing and uses an em dash for unknown leaf index', () => {
        expect(formatLeafJsonPath({
            documentName: 'Sample Act',
            section: {
                section_code: '99',
                section_heading: 'Orphan',
            },
            leafIndex: null,
            leafCount: 2,
        })).toBe(
            [
                'Sample Act',
                'Section 99 · Orphan',
                'Leaf — of 2',
            ].join('\n'),
        );
    });
});
