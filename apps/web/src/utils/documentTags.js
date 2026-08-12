/** Labels + presentation for auto-derived document provenance tags. */

export const SOURCE_KIND_NATIVE = 'native-digital';
export const SOURCE_KIND_SCANNED = 'scanned-ocr';
export const SOURCE_KIND_MIXED = 'mixed-ocr';
export const TAG_PROVISIONAL = 'ocr-provisional';
export const TAG_NEEDS_REVIEW = 'ocr-needs-review';

const TAG_META = {
    [SOURCE_KIND_NATIVE]: {
        label: 'Native digital',
        shortLabel: 'Native',
        className: 'tag-native',
        title: 'Text-layer PDF — no OCR in this parse',
    },
    [SOURCE_KIND_SCANNED]: {
        label: 'Scanned PDF',
        shortLabel: 'Scanned',
        className: 'tag-scanned',
        title: 'Most or all pages were OCR’d',
    },
    [SOURCE_KIND_MIXED]: {
        label: 'Mixed OCR',
        shortLabel: 'Mixed',
        className: 'tag-mixed',
        title: 'Some pages were OCR’d (cover or partial scan)',
    },
    [TAG_PROVISIONAL]: {
        label: 'OCR provisional',
        shortLabel: 'Provisional',
        className: 'tag-provisional',
        title: 'OCR admitted below the fidelity floor',
    },
    [TAG_NEEDS_REVIEW]: {
        label: 'OCR needs review',
        shortLabel: 'Needs OCR review',
        className: 'tag-needs-review',
        title: 'Engine disagreements remain on OCR tokens',
    },
};

export function tagMeta(code) {
    return TAG_META[code] || {
        label: code,
        shortLabel: code,
        className: 'tag-unknown',
        title: code,
    };
}

/** Ordered pills for a document card / review header. */
export function provenancePills(provenance) {
    if (!provenance) return [];
    const codes = Array.isArray(provenance.tags) && provenance.tags.length
        ? provenance.tags
        : provenance.source_kind
            ? [provenance.source_kind]
            : [];
    return codes.map((code) => {
        const meta = tagMeta(code);
        return { code, ...meta };
    });
}

export function provenanceTooltip(provenance) {
    if (!provenance) return '';
    const parts = [];
    if (Number.isFinite(provenance.ocr_pages) && Number.isFinite(provenance.ocr_total_pages)) {
        parts.push(`${provenance.ocr_pages}/${provenance.ocr_total_pages} pages OCR’d`);
    } else if (Number.isFinite(provenance.ocr_pages)) {
        parts.push(`${provenance.ocr_pages} pages OCR’d`);
    }
    if (Number.isFinite(provenance.mean_agreement)) {
        parts.push(`${provenance.mean_agreement}% engine agreement`);
    }
    if (provenance.floor) {
        parts.push(`floor: ${provenance.floor}`);
    }
    return parts.join(' · ');
}

export function healthFacet(health) {
    if (!health || !health.measured_at) return 'unmeasured';
    if (health.gate_ok === true) return 'within_gate';
    if (health.gate_ok === false) return 'outside_gate';
    if (
        Number.isFinite(health.invariants_total)
        && health.invariants_total > 0
    ) {
        return health.invariants_passed === health.invariants_total
            ? 'within_gate'
            : 'outside_gate';
    }
    return 'unmeasured';
}

export function reviewFacet(doc) {
    const total = doc.total_sections || 0;
    const reviewed = doc.stats?.reviewed || 0;
    if (total <= 0 || reviewed <= 0) return 'untouched';
    if (reviewed >= total) return 'complete';
    return 'in_progress';
}

/** True when leaf page range intersects OCR'd pages. */
export function sectionWasOcrd(section, pagesOcred) {
    if (!section || !Array.isArray(pagesOcred) || pagesOcred.length === 0) {
        return false;
    }
    let start = section.start_page ?? section.end_page;
    let end = section.end_page ?? section.start_page;
    if (start == null || end == null) return false;
    if (end < start) [start, end] = [end, start];
    const set = new Set(pagesOcred);
    for (let page = start; page <= end; page += 1) {
        if (set.has(page)) return true;
    }
    return false;
}
