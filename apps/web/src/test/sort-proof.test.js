import { describe, expect, it } from 'vitest';
import { filterDocuments, groupDocumentsByFamily } from '../utils/documentFilters';

const docs = [
    {
        id: '1',
        name: 'Customs Act, 1969 as amended up to 01.01.2020',
        total_pages: 10,
        uploaded_at: '2020-01-01T00:00:00Z',
        stats: { reviewed: 0 },
        total_sections: 10,
        provenance: { source_kind: 'native-digital' },
        corpus_lane: 'customs',
        source_type: 'acts_corpus',
        health: null,
    },
    {
        id: '2',
        name: 'Customs Act, 1969 as amended up to 01.01.2024',
        total_pages: 500,
        uploaded_at: '2024-06-01T00:00:00Z',
        stats: { reviewed: 10 },
        total_sections: 10,
        provenance: { source_kind: 'scanned-ocr' },
        corpus_lane: 'customs',
        source_type: 'acts_corpus',
        health: { measured_at: 'x', gate_ok: false },
    },
    {
        id: '3',
        name: 'Sales Tax Act, 1990 as amended up to 01.01.2022',
        total_pages: 100,
        uploaded_at: '2022-01-01T00:00:00Z',
        stats: { reviewed: 5 },
        total_sections: 10,
        provenance: { source_kind: 'mixed-ocr' },
        corpus_lane: 'sales_tax',
        source_type: 'acts_corpus',
        health: null,
    },
];

describe('library sort vs grouped view', () => {
    it('flat order follows pages sort', () => {
        const filtered = filterDocuments(docs, { facets: {}, sort: 'pages' });
        expect(filtered.map((d) => d.id)).toEqual(['2', '3', '1']);
    });

    it('grouped view respects pages sort across and within families', () => {
        const filtered = filterDocuments(docs, { facets: {}, sort: 'pages' });
        const groups = groupDocumentsByFamily(filtered, 'pages');
        const groupedOrder = groups.flatMap((g) => g.editions.map((d) => d.id));
        expect(groupedOrder).toEqual(['2', '1', '3']);
        // Customs group first (has the 500-page doc), editions by pages within it
        expect(groups[0].editions.map((d) => d.id)).toEqual(['2', '1']);
        expect(groups[1].editions.map((d) => d.id)).toEqual(['3']);
    });

    it('name sort still orders editions by year within a family', () => {
        const filtered = filterDocuments(docs, { facets: { corpusLane: 'customs' }, sort: 'name' });
        const groups = groupDocumentsByFamily(filtered, 'name');
        expect(groups).toHaveLength(1);
        expect(groups[0].editions.map((d) => d.id)).toEqual(['1', '2']);
    });
});
