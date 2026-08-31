/**
 * The browser's second pass over already-sanitized HTML.
 *
 * `backend/services/html_sanitizer.py` sanitizes at ingest and is the first line of
 * defence; this is the second, because stored HTML is a trust boundary. What it is
 * NOT is a second opinion: it used to carry its own, narrower allowlist maintained by
 * hand, and the two had drifted apart in a way that deleted real pipeline output --
 *
 *   * seven classes the backend deliberately keeps (`fn-table`, `omitted-bracket`,
 *     `explanation`, `defn`, `formula`, `frac`, `legend`), measured at 11,349
 *     occurrences across the two corpora, each with a live stylesheet rule;
 *   * and `flex: 0 0 N%`, the footnote-table column widths recovered from the PDF's
 *     own geometry, which `html_sanitizer` has a narrow, audited exception for --
 *     dropped by `FORBID_ATTR: ['style']` in `FootnotePanel`, the only place
 *     `.fn-table` ever renders.
 *
 * The policy is now generated from the Python module
 * (`python -m backend.services.html_sanitizer --write`) and a pytest fails when this
 * file drifts from it, the same way `tools/suite/register.json` is gated.
 */
import DOMPurify from 'dompurify';

import policy from './sanitizerPolicy.json';

const KNOWN_CLASSES = new Set(policy.knownClasses);
const FLEX_BASIS = new RegExp(policy.flexBasisPattern);

DOMPurify.addHook('uponSanitizeAttribute', (_node, data) => {
    if (data.attrName === 'class') {
        data.attrValue = data.attrValue
            .split(/\s+/)
            .filter((name) => KNOWN_CLASSES.has(name))
            .join(' ');
        data.keepAttr = Boolean(data.attrValue);
        return;
    }
    if (data.attrName === 'style') {
        // Exactly the declaration the backend re-emits, matched with the backend's
        // own pattern. Anything else in a style attribute is still dropped.
        const kept = data.attrValue
            .split(';')
            .map((declaration) => declaration.split(':'))
            .filter(([prop, ...rest]) => prop.trim().toLowerCase() === 'flex'
                && FLEX_BASIS.test(rest.join(':').trim()))
            .map(([, ...rest]) => `flex:${rest.join(':').trim()}`)
            .join(';');
        data.attrValue = kept;
        data.keepAttr = Boolean(kept);
    }
});

export const sanitizeLegalHtml = (value) => DOMPurify.sanitize(value || '', {
    ALLOWED_TAGS: policy.allowedTags,
    ALLOWED_ATTR: [...policy.allowedAttrs, 'style'],
    FORBID_TAGS: policy.forbidTags,
    // `style` is filtered by the hook above rather than forbidden outright; `href`,
    // `src` and `srcset` have no place in statutory text and stay out.
    FORBID_ATTR: ['href', 'src', 'srcset'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
});
