import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
    Sun, Moon, ArrowLeft, PanelLeftClose, PanelLeftOpen, BookOpen,
    Library, ListChecks, UploadCloud, Search, User, Keyboard,
} from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';
import CommandPalette from '../ui/CommandPalette';
import ShortcutsHelp from '../ui/ShortcutsHelp';

const NAV_ITEMS = [
    { path: '/', label: 'Triage', icon: ListChecks, match: (p) => p === '/' },
    { path: '/library', label: 'Library', icon: Library, match: (p) => p.startsWith('/library') },
    { path: '/upload', label: 'Upload', icon: UploadCloud, match: (p) => p.startsWith('/upload') },
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
    const setReviewer = useUiStore((s) => s.setReviewer);
    const setCommandPaletteOpen = useUiStore((s) => s.setCommandPaletteOpen);
    const setShortcutsHelpOpen = useUiStore((s) => s.setShortcutsHelpOpen);
    const promptDialog = useUiStore((s) => s.promptDialog);

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
            const typing = e.target.matches?.('input, textarea, select') || e.target.isContentEditable;
            if (e.key === '?' && !typing) {
                e.preventDefault();
                setShortcutsHelpOpen(true);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [setCommandPaletteOpen, setShortcutsHelpOpen]);

    const changeReviewer = async () => {
        const value = await promptDialog({
            title: 'Reviewer name',
            message: 'Shown on review events and notes (attribution only, not authentication).',
            defaultValue: reviewerName === 'anonymous' ? '' : reviewerName,
            confirmLabel: 'Save',
        });
        if (value !== null && value !== undefined) setReviewer(value);
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
                    <div
                        className="brand"
                        onClick={() => navigate('/')}
                        role="link"
                        tabIndex={0}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') navigate('/');
                        }}
                    >
                        <BookOpen size={19} strokeWidth={2.5} />
                        <span>PDF-QA</span>
                    </div>
                    <nav className="top-nav" aria-label="Primary">
                        {NAV_ITEMS.map(({ path, label, icon: Icon, match }) => (
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
                        onClick={changeReviewer}
                        title="Reviewer attribution — click to change"
                    >
                        <User size={13} aria-hidden="true" />
                        <span>{reviewerName === 'anonymous' ? 'Set reviewer' : reviewerName}</span>
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
