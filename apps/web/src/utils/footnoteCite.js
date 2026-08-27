export const MISSING_NOTE = 'This citation has no attached note text.';

/** Match a cite marker (DOM node or string) to a footnote row. */
export const findFootnoteForCite = (citeOrMarker, footnotes) => {
    const marker = (
        typeof citeOrMarker === 'string'
            ? citeOrMarker
            : (citeOrMarker?.textContent || '')
    ).trim();
    if (!marker || !footnotes || footnotes.length === 0) return null;
    return footnotes.find((fn) => {
        const key = String(fn.marker || fn.ref || '').trim();
        return key === marker || key.endsWith(`.${marker}`) || String(fn.ref || '').trim() === marker;
    }) || null;
};

export const footnoteTextForCite = (cite, footnotes) => {
    const fromAttr = (cite.getAttribute('data-footnote-text') || '').trim();
    if (fromAttr) return fromAttr;
    const hit = findFootnoteForCite(cite, footnotes);
    return (hit && hit.text) ? String(hit.text) : '';
};
