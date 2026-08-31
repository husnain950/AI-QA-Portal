/**
 * Edition / family helpers derived from documents.name.
 * Family key is a scope limiter only — wrong keys under-merge, never over-merge.
 */

const DATE_PATTERNS = [
    /(?:amended|upto|up\s*to|as\s+on|dated).{0,40}?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})/i,
    /(?:amended|upto|up\s*to|as\s+on|dated).{0,40}?\b((?:19|20)\d{2})\b/i,
    /\b(20\d{2})\s*[-–]\s*(\d{2})\b/, // 2011-12 — before bare year
    /\b(20\d{2}|19\d{2})\b/,
];

const CANONICAL_FAMILIES = [
    [/^income\s+tax\s+ordinance(?:\s*,?\s*2001)?$/i, 'income tax ordinance, 2001'],
    [/^customs\s+act(?:\s*,?\s*1969)?$/i, 'customs act, 1969'],
    [/^sales\s+tax\s+act(?:\s*,?\s*1990)?$/i, 'sales tax act, 1990'],
    [/^federal\s+excise\s+act(?:\s*,?\s*2005)?$/i, 'federal excise act, 2005'],
];

export function familyKeyFromName(name) {
    const raw = String(name || '').trim();
    if (!raw) return 'unknown';
    let base = raw
        .replace(/\(.*?\)/g, ' ')
        .replace(/\s*[-–]\s*(?=(?:as\s+)?amended|upto|up\s*to|dated)/i, ' ')
        .replace(/,?\s*(as\s+)?amended.*$/i, ' ')
        .replace(/,?\s*upto.*$/i, ' ')
        .replace(/,?\s*up\s*to.*$/i, ' ')
        .replace(/,?\s*dated.*$/i, ' ')
        .replace(/^the\s+/i, ' ')
        .replace(/\s*,\s*/g, ', ')
        .replace(/\s+/g, ' ')
        .trim()
        .replace(/[,\s]+$/g, '')
        .trim()
        .toLowerCase();
    if (!base) return 'unknown';

    for (const [pattern, canonical] of CANONICAL_FAMILIES) {
        if (pattern.test(base)) return canonical;
    }

    const finance = base.match(
        /^(finance(?:\s+supplementary)?\s+act),?\s*(?:19|20)\d{2}(?:\s*[-–]\s*\d{2})?$/i,
    );
    if (finance) return finance[1].toLowerCase();

    return base;
}

export function familyTitleFromKey(familyKey) {
    const raw = String(familyKey || '').trim();
    if (!raw || raw === 'unknown') return 'Unknown statute';
    return raw.charAt(0).toUpperCase() + raw.slice(1);
}

/**
 * @returns {{ year: number | null, sortKey: number, label: string, unknown: boolean }}
 */
export function editionDateFromName(name) {
    const raw = String(name || '');
    for (const re of DATE_PATTERNS) {
        const m = raw.match(re);
        if (!m) continue;
        if (m[2] && m[1] && m[1].length === 4) {
            // 2011-12 style — use first year
            const year = Number(m[1]);
            return { year, sortKey: year, label: String(year), unknown: false };
        }
        const token = m[1];
        if (/^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$/.test(token)) {
            const parts = token.split(/[./-]/);
            let year = Number(parts[2]);
            if (year < 100) year += 2000;
            return { year, sortKey: year, label: String(year), unknown: false };
        }
        const year = Number(token);
        if (year >= 1900 && year <= 2100) {
            return { year, sortKey: year, label: String(year), unknown: false };
        }
    }
    return { year: null, sortKey: 9999, label: 'year unknown', unknown: true };
}

/**
 * The edition of a whole document, preferring the year the SERVER sorted by.
 *
 * `editionDateFromName` reads the name and prefers the year next to
 * "amended upto"; `YEAR_SQL` prefers `edition_date`, else the FIRST 19xx/20xx in
 * the name. For "Customs Act, 1969 as amended up to 30.06.2025" the server sorted
 * on 1969 and the badge read 2025 -- so "Edition — newest" produced an order that
 * contradicted the labels on the cards. Reading the server's value is what makes
 * them agree; the name is the fallback for a payload that carries no year.
 */
export function editionOf(doc) {
    const year = doc?.edition_year;
    if (typeof year === 'number' && Number.isFinite(year)) {
        return { year, sortKey: year, label: String(year), unknown: false };
    }
    return editionDateFromName(doc?.name || doc?.document_name || '');
}

export function sortEditions(docs) {
    return [...docs].sort((a, b) => {
        const da = editionOf(a);
        const db = editionOf(b);
        if (da.sortKey !== db.sortKey) return da.sortKey - db.sortKey;
        return String(a.name || '').localeCompare(String(b.name || ''));
    });
}
