/** Reviewer-local favorites, persisted in localStorage (no server account concept
 * for these). Backed by a zustand store so star toggles re-render everywhere.
 */
import { create } from 'zustand';

const STORAGE_KEY = 'qa-portal-library-favorites';

function readIds() {
    try {
        const parsed = JSON.parse(window.localStorage?.getItem(STORAGE_KEY) || '[]');
        return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : [];
    } catch {
        return [];
    }
}

function writeIds(ids) {
    try {
        window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(ids));
    } catch {
        // storage unavailable (private mode) — favorites live for the session only
    }
}

export const useFavorites = create((set, get) => ({
    ids: readIds(),

    toggle: (id) => {
        const current = get().ids;
        const ids = current.includes(id)
            ? current.filter((existing) => existing !== id)
            : [id, ...current];
        writeIds(ids);
        set({ ids });
    },

    addMany: (toAdd) => {
        const current = get().ids;
        const fresh = toAdd.filter((id) => !current.includes(id));
        if (!fresh.length) return;
        const ids = [...fresh, ...current];
        writeIds(ids);
        set({ ids });
    },

    removeMany: (toRemove) => {
        const drop = new Set(toRemove);
        const ids = get().ids.filter((id) => !drop.has(id));
        writeIds(ids);
        set({ ids });
    },
}));

export function isFavorite(id) {
    return useFavorites.getState().ids.includes(id);
}
