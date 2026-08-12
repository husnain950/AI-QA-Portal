import { describe, expect, it } from 'vitest';
import {
    facetCounts,
    filterDocuments,
    groupDocumentsByFamily,
} from '../utils/documentFilters';
import { familyKeyFromName } from '../utils/editions';

const documents = [
    {
        id: 'ito',
        name: 'Income Tax Ordinance 2001 - amended upto 30th June 2025',
        source_type: 'acts_corpus',
        corpus_lane: 'ordinance',
        total_pages: 400,
        total_sections: 10,
        uploaded_at: '2025-01-01T00:00:00Z',
        stats: { reviewed: 10 },
        health: { measured_at: '2025-01-01', gate_ok: true },
        provenance: { source_kind: 'native-digital', tags: ['native-digital'] },
    },
    {
        id: 'customs-a',
        name: 'Customs Act, 1969 as amended up to 30.06.2025',
        source_type: 'acts_corpus',
        corpus_lane: 'customs',
        total_pages: 200,
        total_sections: 20,
        uploaded_at: '2025-06-01T00:00:00Z',
        stats: { reviewed: 5 },
        health: { measured_at: '2025-06-01', gate_ok: false },
        provenance: { source_kind: 'scanned-ocr', tags: ['scanned-ocr'] },
    },
    {
        id: 'customs-b',
        name: 'The Customs Act, 1969 (Amended upto 30th June 2007)',
        source_type: 'acts_corpus',
        corpus_lane: 'customs',
        total_pages: 180,
        total_sections: 18,
        uploaded_at: '2007-06-01T00:00:00Z',
        stats: { reviewed: 0 },
        health: null,
        provenance: { source_kind: 'native-digital', tags: ['native-digital'] },
    },
    {
        id: 'manual',
        name: 'Manual Ordinance',
        source_type: 'upload',
        corpus_lane: 'manual',
        total_pages: 10,
        total_sections: 4,
        uploaded_at: '2024-01-01T00:00:00Z',
        stats: { reviewed: 0 },
        health: null,
        provenance: { source_kind: 'native-digital', tags: ['native-digital'] },
    },
];

describe('dashboard document filtering', () => {
    it('filters by corpus lane and kind together', () => {
        const filtered = filterDocuments(documents, {
            facets: { corpusLane: 'customs', sourceKind: 'scanned-ocr' },
        });
        expect(filtered.map((doc) => doc.id)).toEqual(['customs-a']);
    });

    it('keeps legacy ACT Corpus filter shape', () => {
        expect(filterDocuments(documents, '', 'acts_corpus').map((doc) => doc.id))
            .toEqual(['customs-a', 'customs-b', 'ito'].sort((a, b) => {
                const names = Object.fromEntries(documents.map((d) => [d.id, d.name]));
                return names[a].localeCompare(names[b]);
            }));
    });

    it('groups customs editions under one family', () => {
        expect(familyKeyFromName(documents[1].name)).toBe(familyKeyFromName(documents[2].name));
        const groups = groupDocumentsByFamily(
            filterDocuments(documents, { facets: { corpusLane: 'customs' } }),
            'name',
        );
        expect(groups).toHaveLength(1);
        expect(groups[0].editions.map((d) => d.id)).toEqual(['customs-b', 'customs-a']);
        expect(groups[0].outsideGate).toBe(true);
    });

    it('counts lanes and kinds', () => {
        const counts = facetCounts(documents);
        expect(counts.lanes.customs).toBe(2);
        expect(counts.lanes.ordinance).toBe(1);
        expect(counts.kinds['scanned-ocr']).toBe(1);
    });
});
