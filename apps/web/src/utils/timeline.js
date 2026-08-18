/**
 * Timeline URLs use query params so family names with spaces/commas never sit
 * in the path (that 404s nginx try_files and blanks the SPA).
 */

export function timelinePath({ sectionId, family, code } = {}) {
    const params = new URLSearchParams();
    if (sectionId) params.set('section_id', sectionId);
    if (family) params.set('family', family);
    if (code) params.set('code', code);
    const qs = params.toString();
    return qs ? `/timeline?${qs}` : '/timeline';
}

export function timelineApiPath({ sectionId, family, code } = {}) {
    const params = new URLSearchParams();
    if (sectionId) {
        params.set('section_id', sectionId);
    } else {
        if (family) params.set('family', family);
        if (code) params.set('section_code', code);
    }
    const qs = params.toString();
    return qs ? `/timeline?${qs}` : '/timeline';
}

function decodePart(value) {
    const raw = String(value || '');
    try {
        return decodeURIComponent(raw);
    } catch {
        return raw;
    }
}

/**
 * Read timeline identity from search params, then from /timeline/:family/:code,
 * then from a leftover encoded splat path.
 */
export function parseTimelineParams({ searchParams, pathFamily, pathCode, splat } = {}) {
    const sectionId = String(searchParams?.get?.('section_id') || '').trim();
    let family = String(searchParams?.get?.('family') || pathFamily || '').trim();
    let code = String(
        searchParams?.get?.('code')
        || searchParams?.get?.('section_code')
        || pathCode
        || '',
    ).trim();

    if ((!family || !code) && splat) {
        const parts = String(splat).split('/').filter(Boolean);
        if (parts.length >= 2) {
            const rawCode = parts.pop();
            const rawFamily = parts.join('/');
            if (!code) code = decodePart(rawCode);
            if (!family) family = decodePart(rawFamily);
        }
    }

    return { sectionId, family, code };
}
