import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
    Sun, Moon, ArrowLeft, PanelLeftClose, PanelLeftOpen, BookOpen,
    Library, ListChecks, UploadCloud, Search, User, Keyboard,
} from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';
import { authApi } from '../../utils/auth';
import { hasRole } from '../../utils/reviewer';
import CommandPalette from '../ui/CommandPalette';
import ShortcutsHelp from '../ui/ShortcutsHelp';
import { isTypingTarget } from '../../utils/keyboard';

const NAV_ITEMS = [
    { path: '/', label: 'Triage', icon: ListChecks, match: (p) => p === '/' },
    { path: '/library', label: 'Library', icon: Library, match: (p) => p.startsWith('/library') },
    // Upload changes the corpus, so it is the admin's. The server refuses it either
    // way; hiding the tab keeps a reviewer from walking into a 403.
    { path: '/upload', label: 'Upload', icon: UploadCloud, match: (p) => p.startsWith('/upload'), role: 'admin' },
];

const AppShell = ({
    children,
    title,
    showBackButton = false,
    backTo = '/',
    sidebarContent = null,
    actions = null,
    scrollable = false,
}) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { theme, toggleTheme, sidebarOpen, toggleSidebar } = useUiStore();
    const reviewerName = useUiStore((s) => s.reviewerName);
    const setCommandPaletteOpen = useUiStore((s) => s.setCommandPaletteOpen);
    const setShortcutsHelpOpen = useUiStore((s) => s.setShortcutsHelpOpen);
    const confirmDialog = useUiStore((s) => s.confirmDialog);

    // Keep the browser tab meaningful.
    useEffect(() => {
        document.title = title ? `${title} · PDF-QA Portal` : 'PDF-QA Portal';
    }, [title]);

    // Global shortcuts: Ctrl/Cmd+K palette, ? shortcut help.
    useEffect(() => {
        const onKey = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                setCommandPaletteOpen(true);
                return;
            }
            const typing = isTypingTarget(e);
            if (e.key === '?' && !typing) {
                e.preventDefault();
                setShortcutsHelpOpen(true);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [setCommandPaletteOpen, setShortcutsHelpOpen]);

    const signOut = async () => {
        // confirmDialog, not promptDialog: this asks a yes/no question, and
        // promptDialog ignored the `confirmOnly` flag that was passed to suppress
        // its text input, so signing out offered a stray box to type in.
        const confirmed = await confirmDialog({
            title: 'Sign out',
            message: `Signed in as ${reviewerName}. Sign out of this browser?`,
            confirmLabel: 'Sign out',
        });
        if (!confirmed) return;
        await authApi.logout();
        window.location.reload();
    };

    return (
        <div className="app-shell">
            <header className="top-bar">
                <div className="top-bar-left">
                    {showBackButton && (
                        <button
                            className="btn btn-ghost btn-icon"
                            onClick={() => navigate(backTo)}
                            title="Back"
                            aria-label="Back"
                        >
                            <ArrowLeft size={17} />
                        </button>
                    )}
                    {sidebarContent && (
                        <button
                            className="btn btn-ghost btn-icon"
                            onClick={toggleSidebar}
                            title={sidebarOpen ? 'Hide navigation sidebar' : 'Show navigation sidebar'}
                            aria-label={sidebarOpen ? 'Hide navigation sidebar' : 'Show navigation sidebar'}
                        >
                            {sidebarOpen ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
                        </button>
                    )}
                    <button
                        type="button"
                        className="brand"
                        onClick={() => navigate('/')}
                        aria-label="Go to Triage"
                    >
                        <BookOpen size={19} strokeWidth={2.5} />
                        <span>PDF-QA</span>
                    </button>
                    <nav className="top-nav" aria-label="Primary">
                        {NAV_ITEMS.filter(({ role }) => !role || hasRole(role))
                            .map(({ path, label, icon: Icon, match }) => (
                            <button
                                key={path}
                                type="button"
                                className={`top-nav-item ${match(location.pathname) ? 'active' : ''}`}
                                aria-current={match(location.pathname) ? 'page' : undefined}
                                onClick={() => navigate(path)}
                            >
                                <Icon size={14} aria-hidden="true" />
                                <span>{label}</span>
                            </button>
                        ))}
                    </nav>
                    {title && <div className="app-title" title={title}>{title}</div>}
                </div>

                <div className="top-bar-right">
                    {actions}
                    <button
                        type="button"
                        className="palette-trigger"
                        onClick={() => setCommandPaletteOpen(true)}
                        title="Command palette (Ctrl+K)"
                    >
                        <Search size={13} aria-hidden="true" />
                        <span>Jump to…</span>
                        <kbd>Ctrl K</kbd>
                    </button>
                    <button
                        type="button"
                        className="reviewer-chip"
                        onClick={signOut}
                        title="Signed in — click to sign out"
                    >
                        <User size={13} aria-hidden="true" />
                        <span>{reviewerName || 'Signed in'}</span>
                    </button>
                    <button
                        className="btn btn-ghost btn-icon"
                        onClick={() => setShortcutsHelpOpen(true)}
                        title="Keyboard shortcuts (?)"
                        aria-label="Keyboard shortcuts"
                    >
                        <Keyboard size={16} />
                    </button>
                    <button
                        className="btn btn-ghost btn-icon"
                        onClick={toggleTheme}
                        title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
                        aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
                    >
                        {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
                    </button>
                </div>
            </header>

            <div className="workspace-container">
                {sidebarContent && (
                    <aside className={`sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
                        {sidebarContent}
                    </aside>
                )}
                <main className={`main-content ${scrollable ? 'scrollable' : ''}`}>
                    {children}
                </main>
            </div>

            <CommandPalette />
            <ShortcutsHelp />
        </div>
    );
};

export default AppShell;
