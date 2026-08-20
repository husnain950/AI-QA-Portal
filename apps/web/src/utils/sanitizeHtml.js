import DOMPurify from 'dompurify';

const ALLOWED_TAGS = [
    'article', 'b', 'blockquote', 'br', 'caption', 'code', 'col', 'colgroup', 'dd',
    'div', 'dl', 'dt', 'em', 'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5',
    'h6', 'hr', 'i', 'li', 'ol', 'p', 'pre', 's', 'section', 'span', 'strong', 'sub',
    'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
];
const ALLOWED_ATTR = [
    'class', 'title', 'lang', 'dir', 'colspan', 'rowspan', 'headers', 'scope', 'abbr',
    'start', 'reversed', 'type', 'value', 'span', 'data-ref',
];
const KNOWN_CLASSES = new Set([
    'section-heading', 'schedule-heading', 'subsection', 'paragraph', 'subparagraph',
    'clause', 'subclause', 'cite', 'citation', 'footnote', 'footnote-marker', 'marker',
    'proviso', 'fbr-table', 'table',
    'table-responsive', 'crx-align-center', 'crx-align-right', 'crx-align-justify',
    'crx-bold', 'crx-italic', 'crx-underline', 'crx-list-unstyled', 'crx-pad-zero',
    'crx-indent-1', 'crx-indent-2', 'crx-indent-3', 'crx-indent-4', 'crx-super', 'crx-sub',
]);

DOMPurify.addHook('uponSanitizeAttribute', (_node, data) => {
    if (data.attrName === 'class') {
        data.attrValue = data.attrValue
            .split(/\s+/)
            .filter((name) => KNOWN_CLASSES.has(name))
            .join(' ');
        data.keepAttr = Boolean(data.attrValue);
    }
});

export const sanitizeLegalHtml = (value) => DOMPurify.sanitize(value || '', {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORBID_TAGS: ['script', 'style', 'svg', 'math', 'iframe', 'object', 'embed', 'audio', 'video', 'img', 'source'],
    FORBID_ATTR: ['style', 'href', 'src', 'srcset'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
});
