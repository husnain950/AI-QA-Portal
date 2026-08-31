export const MISSING_NOTE = 'This citation has no attached note text.';

/**
 * Match a cite to its footnote row.
 *
 * `data-ref` first. The pipeline emits it on every `<sup class="cite">`, the backend
 * sanitizer allowlists it and the client sanitizer keeps it -- an explicit identifier
 * carried the whole way down and then ignored, while this resolved by rendered text
 * instead. That fallback matches `ref` values by suffix (`endsWith('.' + marker)`)
 * and takes the FIRST hit, so a marker that repeats across pages of one leaf links to
 * whichever footnote happens to come first.
 *
 * The text path stays for the pre-`data-ref` corpus, which is most of it until the
 * re-conversion runs.
 */
export const findFootnoteForCite = (citeOrMarker, footnotes) => {
    if (!footnotes || footnotes.length === 0) return null;

    if (typeof citeOrMarker !== 'string') {
        const ref = (citeOrMarker?.getAttribute?.('data-ref') || '').trim();
        if (ref) {
            const exact = footnotes.find((fn) => String(fn.ref || '').trim() === ref);
            if (exact) return exact;
        }
    }

    const marker = (
        typeof citeOrMarker === 'string'
            ? citeOrMarker
            : (citeOrMarker?.textContent || '')
    ).trim();
    if (!marker) return null;
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
