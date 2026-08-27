/** Relative time for list metadata ("added 3d ago"). */

export function timeAgo(iso) {
    if (!iso) return null;
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

/** YYYY-MM-DD for n days ago — Date-added filter presets. */
export function isoDateDaysAgo(days) {
    const date = new Date(Date.now() - days * 86_400_000);
    return date.toISOString().slice(0, 10);
}

export function fullDateTime(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? String(iso) : date.toLocaleString();
}
