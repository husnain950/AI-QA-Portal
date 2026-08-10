/**
 * Edition / family helpers derived from documents.name.
 * Family key is a scope limiter only — wrong keys under-merge, never over-merge.
 */

const DATE_PATTERNS = [
    /(?:amended|upto|up\s*to|as\s+on|dated)\s*(?:upto\s*)?(\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4})/i,
    /\b(20\d{2}|19\d{2})\b/,
    /\b(20\d{2})\s*[-–]\s*(\d{2})\b/, // 2011-12
];

export function familyKeyFromName(name) {
    const raw = String(name || '').trim();
    if (!raw) return 'unknown';
    let base = raw
        .replace(/\(.*?\)/g, ' ')
        .replace(/,?\s*(as\s+)?amended.*$/i, ' ')
        .replace(/,?\s*upto.*$/i, ' ')
        .replace(/,?\s*dated.*$/i, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    base = base.replace(/[,\s]+$/g, '').trim();
    return base.toLowerCase() || 'unknown';
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
        if (/^\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4}$/.test(token)) {
            const parts = token.split(/[.\/-]/);
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

export function sortEditions(docs) {
    return [...docs].sort((a, b) => {
        const da = editionDateFromName(a.name || a.document_name || '');
        const db = editionDateFromName(b.name || b.document_name || '');
        if (da.sortKey !== db.sortKey) return da.sortKey - db.sortKey;
        return String(a.name || '').localeCompare(String(b.name || ''));
    });
}
