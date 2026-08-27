/** Recently viewed documents (newest first), reviewer-local in localStorage.
 * Recorded at the single choke point every open path funnels through: the
 * Review page mounting a document.
 */
import { create } from 'zustand';

const STORAGE_KEY = 'qa-portal-library-recents';
const CAP = 50;

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
        // storage unavailable — recents live for the session only
    }
}

export const useRecents = create((set, get) => ({
    ids: readIds(),

    record: (id) => {
        if (!id) return;
        const ids = [id, ...get().ids.filter((existing) => existing !== id)].slice(0, CAP);
        writeIds(ids);
        set({ ids });
    },

    clear: () => {
        writeIds([]);
        set({ ids: [] });
    },
}));

export function recordDocumentView(id) {
    useRecents.getState().record(id);
}
