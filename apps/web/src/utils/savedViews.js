/** Named snapshots of the Library URL state (filters + sort + view). Local to
 * this browser — the URL itself is the shareable form. */
import { create } from 'zustand';

const STORAGE_KEY = 'qa-portal-library-saved-views';

function readViews() {
    try {
        const parsed = JSON.parse(window.localStorage?.getItem(STORAGE_KEY) || '[]');
        return Array.isArray(parsed)
            ? parsed.filter((view) => view && typeof view.name === 'string' && typeof view.search === 'string')
            : [];
    } catch {
        return [];
    }
}

function writeViews(views) {
    try {
        window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(views));
    } catch {
        // storage unavailable — saved views live for the session only
    }
}

export const useSavedViews = create((set, get) => ({
    views: readViews(),

    save: (name, search) => {
        const views = [
            { name, search, savedAt: new Date().toISOString() },
            ...get().views.filter((view) => view.name !== name),
        ].slice(0, 20);
        writeViews(views);
        set({ views });
    },

    remove: (name) => {
        const views = get().views.filter((view) => view.name !== name);
        writeViews(views);
        set({ views });
    },
}));
