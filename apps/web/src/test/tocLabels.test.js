import { describe, expect, it } from 'vitest';
import {
    cleanHeading,
    formatHierarchyLabel,
    formatLeafIdentity,
    formatSectionLabel,
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

    it('cleans gazette junk, leading brackets, and dot leaders', () => {
        expect(cleanHeading('] THE GAZETTE OF PAKISTAN, EXTRA.')).toBe('');
        expect(cleanHeading('Definitions................')).toBe('Definitions');
        expect(
            cleanHeading('Short title, extent and commencement. ………..7'),
        ).toBe('Short title, extent and commencement');
        expect(cleanHeading('Uniform 14')).toBe('Uniform 14');
        expect(
            cleanHeading('CHAPTER III Officers of Customs Section Page No. 12'),
        ).toMatch(/CHAPTER III/);
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
