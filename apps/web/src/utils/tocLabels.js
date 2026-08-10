// A code that names a container must not be prefixed with "Section ". Matching only
// the FIRST word missed every schedule the corpus actually prints — "THE FIRST
// SCHEDULE", "SIXTH SCHEDULE" — plus annexures and Contents, so 5,393 leaves read as
// "Section THE FIRST SCHEDULE". SCHEDULE is therefore matched anywhere in the code.
const CONTAINER_CODE_RE =
    /(^(?:THE\s+)?(PART|CHAPTER|DIVISION|PREAMBLE|SECTION|CONTENTS|ANNEX))|(\bSCHEDULE\b)/i;
const SCHEDULE_RE = /\bschedule\b/i;
const DOT_LEADERS_RE = /(?:[.\u2026·•]{2,}|\u2026+)/g;
const LEADING_JUNK_RE = /^[\]\s|]+/;
const GAZETTE_RE = /THE\s+GAZETTE\s+OF\s+PAKISTAN/i;
const CONTENTS_MARKER_RE = /Section\s+Page\s+No\.?/i;
const TRAILING_TOC_PAGE_RE =
    /[\s.·•…]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?(?:\s+Chapter[-–]?\s*[IVXLC0-9]+)?\s*$/i;
const GAZETTE_PREFIX_RE = new RegExp(
    '^\\]?\\s*THE\\s+GAZETTE\\s+OF\\s+PAKISTAN'
    + '(?:[\\s,.]|EXTRA\\.?|EXTRAORDINARY|ISLAMABAD|'
    + 'MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY|'
    + 'JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|'
    + 'OCTOBER|NOVEMBER|DECEMBER|'
    + '\\d{1,4})*',
    'i',
);

/**
 * Light display cleanup for TOC / breadcrumb-style headings.
 */
export function cleanHeading(heading) {
    let text = String(heading || '').trim();
    if (!text) return '';

    text = text.replace(LEADING_JUNK_RE, '');
    const hadGazette = GAZETTE_RE.test(text);
    const hadLeaders = /(?:[.\u2026·•]{2,}|\u2026+)/.test(text);
    const hadContents = CONTENTS_MARKER_RE.test(text);

    if (hadGazette) {
        text = text.replace(GAZETTE_PREFIX_RE, '').trim();
    }
    if (hadLeaders) {
        text = text.replace(DOT_LEADERS_RE, ' ');
    }
    text = text.replace(/\s+/g, ' ').trim();

    if (hadGazette || hadLeaders || hadContents) {
        text = text.replace(TRAILING_TOC_PAGE_RE, '').replace(/[ .·•…]+$/g, '').trim();
    }
    if (hadContents) {
        text = text.replace(CONTENTS_MARKER_RE, '').trim();
    }

    return text;
}

/**
 * Resolve chapter vs schedule for breadcrumb/TOC chrome.
 * Prefers persisted hierarchy_kind; falls back to /\bschedule\b/i on code/heading.
 */
export function resolveHierarchyKind(hierarchyKind, code, heading) {
    const kind = String(hierarchyKind || '').trim().toLowerCase();
    if (kind === 'schedule' || kind === 'chapter') return kind;
    const haystack = `${code || ''} ${heading || ''}`;
    if (SCHEDULE_RE.test(haystack)) return 'schedule';
    return 'chapter';
}

export function hierarchyTypeLabel(hierarchyKind, code, heading) {
    return resolveHierarchyKind(hierarchyKind, code, heading) === 'schedule'
        ? 'Schedule'
        : 'Chapter';
}

export function formatHierarchyLabel(code, heading, hierarchyKind) {
    const cleanedCode = String(code || '').trim();
    const cleanedHeading = cleanHeading(heading);
    if (!cleanedCode && !cleanedHeading) return null;

    const kind = resolveHierarchyKind(hierarchyKind, cleanedCode, cleanedHeading);
    // Only inject Schedule chrome when the code itself is not already schedule-named.
    // Do not rewrite ordinary chapter/part/division labels.
    if (
        kind === 'schedule'
        && cleanedCode
        && !SCHEDULE_RE.test(cleanedCode)
        && !CONTAINER_CODE_RE.test(cleanedCode)
    ) {
        if (!cleanedHeading) return `Schedule ${cleanedCode}`;
        return `Schedule ${cleanedCode}: ${cleanedHeading}`;
    }

    if (!cleanedHeading) return cleanedCode;
    if (!cleanedCode) return cleanedHeading;
    return `${cleanedCode}: ${cleanedHeading}`;
}

export function formatSectionLabel(code, heading, _startPage) {
    const cleanedCode = String(code || '').trim();
    const cleanedHeading = cleanHeading(heading);
    const isContainer = CONTAINER_CODE_RE.test(cleanedCode);
    const prefix = isContainer || !cleanedCode ? '' : 'Section ';

    // Empty code+heading leaves (e.g. loose tables) must not invent p.N labels.
    if (!cleanedCode && !cleanedHeading) {
        return null;
    }
    if (!cleanedHeading) return `${prefix}${cleanedCode}`.trim();
    if (!cleanedCode) return cleanedHeading;
    return `${prefix}${cleanedCode}: ${cleanedHeading}`;
}

/** Statute identity for facts bar — never invent blank titles. */
export function formatLeafIdentity(code, heading) {
    return formatSectionLabel(code, heading) || 'Untitled leaf';
}
