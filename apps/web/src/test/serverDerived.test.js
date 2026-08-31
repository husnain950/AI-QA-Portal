/**
 * The client reads what the server derived; it does not derive it again.
 *
 * Every one of these had a client-side copy that had drifted from the expression the
 * server actually uses, and each drift was visible in the UI:
 *
 *   lane        filtering by Source = Customs returned a card badged "Other Acts"
 *   year        "Edition — newest" produced an order contradicting the card labels
 *   family      5 of 29 server families split into 34 client groups on the real
 *               corpus, the 21-edition Income Tax Ordinance among them
 */
import { describe, expect, it } from 'vitest';

import { documentLane } from '../utils/corpusLanes';
import { editionOf, familyKeyFromName } from '../utils/editions';
import { groupDocumentsByFamily } from '../utils/libraryQuery';

describe('lane', () => {
    it('uses the lane the server resolved, not the raw column', () => {
        // LANE_SQL classifies a NULL corpus_lane by title; the old client code
        // collapsed every such row to other_acts, so the badge contradicted the
        // filter that returned the row.
        expect(documentLane({
            lane: 'customs', corpus_lane: null, source_type: 'acts_corpus',
        })).toBe('customs');
    });

    it('falls back only when the server sent no lane at all', () => {
        expect(documentLane({ corpus_lane: 'sales_tax' })).toBe('sales_tax');
        expect(documentLane({ source_type: 'acts_corpus' })).toBe('other_acts');
        expect(documentLane({})).toBe('manual');
    });
});

describe('edition year', () => {
    it('uses the year the server sorted on', () => {
        // The server sorts on the FIRST 19xx/20xx in the name; reading the name the
        // client's own way gives 2025 here, and the list order would disagree with
        // the label on every card.
        const doc = { name: 'Customs Act, 1969 as amended up to 30.06.2025', edition_year: 1969 };
        expect(editionOf(doc).label).toBe('1969');
    });

    it('falls back to the name when no year was sent', () => {
        expect(editionOf({ name: 'Finance Act, 2014' }).label).toBe('2014');
        expect(editionOf({ name: 'Untitled' }).unknown).toBe(true);
    });
});

describe('statute family', () => {
    // Both real names, and the real server family they belong to.
    const editions = [
        { id: 'a', name: 'Sales Tax Rules 2006 updated upto 30-06-2025',
          family_key: 'sales tax rules, 2006', family_title: 'Sales tax rules, 2006' },
        { id: 'b', name: 'Sales Tax Rules, 2006 (Updated upto 01-01-2025)',
          family_key: 'sales tax rules, 2006', family_title: 'Sales tax rules, 2006' },
    ];

    it('groups on the key the server assigned', () => {
        const groups = groupDocumentsByFamily(editions);
        expect(groups).toHaveLength(1);
        expect(groups[0].familyKey).toBe('sales tax rules, 2006');
        expect(groups[0].editions).toHaveLength(2);
        expect(groups[0].title).toBe('Sales tax rules, 2006');
    });

    it('and the client key really would have split them', () => {
        // The regression this replaces, pinned so nobody reinstates the derivation:
        // the unanchored `dated` pattern eats the "UP" of "UPDATED UPTO", so the
        // bare name and the parenthesised one land in different groups.
        const keys = new Set(editions.map((doc) => familyKeyFromName(doc.name)));
        expect(keys.size).toBe(2);
        expect([...keys].sort()).toEqual(['sales tax rules 2006 up', 'sales tax rules, 2006']);
    });

    it('still groups documents that carry no family key', () => {
        const groups = groupDocumentsByFamily([
            { id: 'x', name: 'Finance Act, 2014' },
            { id: 'y', name: 'Finance Act, 2015' },
        ]);
        expect(groups).toHaveLength(1);
        expect(groups[0].familyKey).toBe('finance act');
    });
});
