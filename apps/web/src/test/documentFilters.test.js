import { describe, expect, it } from 'vitest';
import { filterDocuments } from '../utils/documentFilters';

const documents = [
    { id: '3', name: 'Manual Ordinance', source_type: 'upload' },
    { id: '2', name: 'Finance Act, 2025', source_type: 'acts_corpus' },
    { id: '1', name: 'Companies Act, 2017', source_type: 'acts_corpus' },
];

describe('dashboard document filtering', () => {
    it('combines title and ACT Corpus filters and sorts by title', () => {
        expect(filterDocuments(documents, 'act', 'acts_corpus').map((doc) => doc.id))
            .toEqual(['1', '2']);
        expect(filterDocuments(documents, 'finance', 'acts_corpus').map((doc) => doc.id))
            .toEqual(['2']);
    });

    it('keeps legacy documents in Manual Uploads', () => {
        expect(filterDocuments(documents, '', 'upload').map((doc) => doc.id))
            .toEqual(['3']);
    });
});
