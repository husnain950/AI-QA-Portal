export const MISSING_NOTE = 'This citation has no attached note text.';

export const footnoteTextForCite = (cite, footnotes) => {
    const fromAttr = (cite.getAttribute('data-footnote-text') || '').trim();
    if (fromAttr) return fromAttr;
    const marker = (cite.textContent || '').trim();
    if (!marker || !footnotes || footnotes.length === 0) return '';
    const hit = footnotes.find((fn) => {
        const key = String(fn.marker || fn.ref || '');
        return key === marker || key.endsWith(`.${marker}`) || String(fn.ref || '') === marker;
    });
    return (hit && hit.text) ? String(hit.text) : '';
};
