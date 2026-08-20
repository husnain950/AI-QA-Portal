const REVIEWER_KEY = 'crx-reviewer-name';

export function getReviewerName() {
    try {
        const stored = window.localStorage?.getItem(REVIEWER_KEY);
        if (stored && stored.trim()) return stored.trim();
    } catch {
        // localStorage unavailable
    }
    return '';
}

export function setReviewerName(name) {
    const value = String(name || '').trim();
    try {
        window.localStorage?.setItem(REVIEWER_KEY, value);
    } catch {
        // localStorage unavailable
    }
    return value;
}
