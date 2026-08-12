/**
 * Pure helpers for the AI fix loop UI (kept out of components for testability).
 */

/** Must match backend.services.ai_fix.MAX_PAGES_SENT — pages attached to the model. */
export const MAX_PAGES_SENT = 4;

/** 1-based PDF pages the model is shown for this leaf (capped like the backend). */
export function pagesSentToModel(startPage, endPage, maxPages = MAX_PAGES_SENT) {
    let first = Number.parseInt(startPage, 10);
    let last = Number.parseInt(endPage, 10);
    if (!Number.isFinite(first) || first < 1) first = 1;
    if (!Number.isFinite(last) || last < 1) last = first;
    if (last < first) [first, last] = [last, first];
    const pages = [];
    for (let page = first; page <= last && pages.length < maxPages; page += 1) {
        pages.push(page);
    }
    return pages;
}

/** Kind of a unified-diff line, for styling: 'add' | 'del' | 'hunk' | 'ctx'. */
export function classifyDiffLine(line) {
    const text = String(line ?? '');
    if (text.startsWith('@@')) return 'hunk';
    if (text.startsWith('+')) return 'add';
    if (text.startsWith('-')) return 'del';
    return 'ctx';
}

/** Split validation issues into { errors, warnings } lists of messages. */
export function validationSummary(issues) {
    const errors = [];
    const warnings = [];
    for (const issue of issues || []) {
        if (!issue || !issue.message) continue;
        (issue.level === 'error' ? errors : warnings).push(issue.message);
    }
    return { errors, warnings, blocked: errors.length > 0 };
}

/** Seed the instructions textarea from the section's open annotations. */
export function seedInstructions(annotations) {
    const open = (annotations || []).filter(
        (annotation) => annotation && annotation.status === 'open',
    );
    if (!open.length) return '';
    const lines = open.map((annotation) => {
        const quoted = String(annotation.highlighted_text || '').slice(0, 120);
        const description = String(annotation.issue_description || '').trim();
        return description ? `- "${quoted}": ${description}` : `- "${quoted}"`;
    });
    return `The following passages were flagged during review:\n${lines.join('\n')}`;
}

/** Tag-class tokens in document order, e.g. ['h4.section-heading', 'p.proviso']. */
export function htmlShape(html) {
    return [...String(html || '').matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/gi)].map((match) => {
        const tag = match[1].toLowerCase();
        const className = (match[2].match(/class\s*=\s*["']([^"']+)/i)?.[1] || '')
            .trim()
            .split(/\s+/)[0];
        return className ? `${tag}.${className}` : tag;
    });
}

/** Short hints when wording is unchanged but markup moved (span→p, etc.). */
export function htmlChangeHints(beforeHtml, afterHtml) {
    const before = htmlShape(beforeHtml);
    const after = htmlShape(afterHtml);
    if (before.join() === after.join()) return [];
    const beforeCounts = {};
    const afterCounts = {};
    for (const token of before) beforeCounts[token] = (beforeCounts[token] || 0) + 1;
    for (const token of after) afterCounts[token] = (afterCounts[token] || 0) + 1;
    const hints = [];
    const keys = new Set([...Object.keys(beforeCounts), ...Object.keys(afterCounts)]);
    for (const key of keys) {
        const delta = (afterCounts[key] || 0) - (beforeCounts[key] || 0);
        if (delta === 0) continue;
        hints.push(`${key} ${delta > 0 ? '+' : ''}${delta}`);
    }
    return hints.slice(0, 6);
}

/** Human summary lines from the proposal's diff stats. */
export function changeSummary(diff) {
    const stats = diff?.stats;
    if (!stats) return [];
    const lines = [];
    const charDelta = (stats.chars_after ?? 0) - (stats.chars_before ?? 0);
    if (charDelta !== 0) {
        lines.push(
            `${Math.abs(charDelta).toLocaleString()} characters ${charDelta > 0 ? 'added' : 'removed'}`,
        );
    }
    const footnoteDelta = (stats.footnotes_after ?? 0) - (stats.footnotes_before ?? 0);
    if (footnoteDelta !== 0) {
        lines.push(
            `${Math.abs(footnoteDelta)} footnote${Math.abs(footnoteDelta) === 1 ? '' : 's'} ${footnoteDelta > 0 ? 'added' : 'removed'}`,
        );
    }
    if (!lines.length && (diff?.plain_text_diff?.length ?? 0) > 0) {
        lines.push('wording changed with no net length change');
    }
    return lines;
}

/** Map a leaf's footnotes (DB row or model JSON) onto HtmlPanel's shape. */
export function panelFootnotes(raw) {
    return (raw || []).map((footnote, index) => ({
        id: footnote.id || String(footnote.ref || footnote.marker || index),
        marker: footnote.marker,
        page: footnote.page ?? null,
        text: footnote.text || '',
        html_content: footnote.html_content || footnote.html || '',
        review_status: footnote.review_status || 'pending',
    }));
}

/** True when this section already has an approved AI fix on record. */
export function hasApprovedFix(proposals, sectionId) {
    return (proposals || []).some(
        (proposal) => proposal.section_id === sectionId && proposal.status === 'approved',
    );
}
