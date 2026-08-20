import { create } from 'zustand';
import { getReviewerName } from '../utils/reviewer';

const getInitialTheme = () => {
    if (typeof window !== 'undefined') {
        try {
            const storedTheme = window.localStorage?.getItem('qa-portal-theme');
            if (storedTheme) return storedTheme;

            const systemPrefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches;
            return systemPrefersDark ? 'dark' : 'light';
        } catch {
            return 'light';
        }
    }
    return 'light';
};

let toastSeq = 0;

export const useUiStore = create((set, get) => {
    const initialTheme = getInitialTheme();
    if (typeof document !== 'undefined') {
        document.documentElement.setAttribute('data-theme', initialTheme);
    }

    return {
        theme: initialTheme,
        sidebarOpen: true,
        sidebarTab: 'toc',
        splitRatio: 0.5,
        pdfZoom: 1.0,
        toasts: [],
        dialog: null, // { title, message, confirmLabel, cancelLabel, resolve }
        hoveredDivergenceId: null,
        commandPaletteOpen: false,
        shortcutsHelpOpen: false,
        reviewerName: getReviewerName(),

        setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
        setShortcutsHelpOpen: (open) => set({ shortcutsHelpOpen: open }),
        // Mirror of the authenticated principal, set by App. Not editable: the server
        // attributes every change to the session, so a typed name would be a lie.
        setReviewerName: (name) => set({ reviewerName: name || '' }),

        toggleTheme: () => set((state) => {
            const newTheme = state.theme === 'light' ? 'dark' : 'light';
            try {
                window.localStorage?.setItem('qa-portal-theme', newTheme);
            } catch {}
            if (typeof document !== 'undefined') {
                document.documentElement.setAttribute('data-theme', newTheme);
            }
            return { theme: newTheme };
        }),

        setSidebarOpen: (open) => set({ sidebarOpen: open }),
        toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
        setSidebarTab: (tab) => set({ sidebarTab: tab }),
        setSplitRatio: (ratio) => set({ splitRatio: ratio }),
        setPdfZoom: (zoom) => set({ pdfZoom: zoom }),
        zoomIn: () => set((state) => ({ pdfZoom: Math.min(3.0, state.pdfZoom + 0.25) })),
        zoomOut: () => set((state) => ({ pdfZoom: Math.max(0.5, state.pdfZoom - 0.25) })),
        resetZoom: () => set({ pdfZoom: 1.0 }),
        setHoveredDivergenceId: (id) => set({ hoveredDivergenceId: id }),

        pushToast: ({ type = 'info', message, durationMs = 8000, onUndo = null } = {}) => {
            const id = ++toastSeq;
            set((state) => ({
                // Cap the stack so a burst of toasts never covers the screen.
                toasts: [...state.toasts, { id, type, message, onUndo, durationMs }].slice(-4),
            }));
            return id;
        },

        dismissToast: (id) => set((state) => ({
            toasts: state.toasts.filter((t) => t.id !== id),
        })),

        confirmDialog: ({ title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel' } = {}) =>
            new Promise((resolve) => {
                set({
                    dialog: { title, message, confirmLabel, cancelLabel, resolve },
                });
            }),

        closeDialog: (result) => {
            const dialog = get().dialog;
            // Prompt dialogs resolve with the entered string (or null on cancel);
            // confirm dialogs resolve with a boolean.
            if (dialog?.resolve) dialog.resolve(dialog.prompt ? result : Boolean(result));
            set({ dialog: null });
        },

        promptDialog: ({ title, message, defaultValue = '', confirmLabel = 'OK', cancelLabel = 'Cancel' } = {}) =>
            new Promise((resolve) => {
                set({
                    dialog: {
                        title,
                        message,
                        confirmLabel,
                        cancelLabel,
                        prompt: true,
                        defaultValue,
                        resolve,
                    },
                });
            }),
    };
});
