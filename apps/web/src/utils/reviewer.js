const REVIEWER_KEY = 'qa-portal-reviewer';

export function getReviewerName() {
    try {
        const stored = window.localStorage?.getItem(REVIEWER_KEY);
        if (stored && stored.trim()) return stored.trim();
    } catch {
        // localStorage unavailable
    }
    return 'anonymous';
}

export function setReviewerName(name) {
    const value = String(name || '').trim() || 'anonymous';
    try {
        window.localStorage?.setItem(REVIEWER_KEY, value);
    } catch {
        // localStorage unavailable
    }
    return value;
}
