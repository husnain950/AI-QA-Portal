import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Sun, Moon, ArrowLeft, PanelLeftClose, PanelLeftOpen, BookOpen, Library, ListChecks } from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';

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
    const onTriage = location.pathname === '/';
    const onLibrary = location.pathname.startsWith('/library');

    return (
        <div className="app-shell">
            <header className="top-bar glass-panel">
                <div className="flex align-center gap-4">
                    {showBackButton && (
                        <button
                            className="btn btn-secondary btn-icon"
                            onClick={() => navigate(backTo)}
                            title="Back"
                        >
                            <ArrowLeft size={18} />
                        </button>
                    )}
                    {sidebarContent && (
                        <button
                            className="btn btn-secondary btn-icon"
                            onClick={toggleSidebar}
                            title={sidebarOpen ? 'Hide Navigation Sidebar' : 'Show Navigation Sidebar'}
                        >
                            {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
                        </button>
                    )}
                    <div className="brand" onClick={() => navigate('/')}>
                        <BookOpen size={22} strokeWidth={2.5} />
                        <span>PDF-QA Portal</span>
                    </div>
                    <nav className="flex align-center gap-1" aria-label="Primary">
                        <button
                            type="button"
                            className={`btn ${onTriage ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '6px 10px', fontSize: '0.75rem', display: 'flex', gap: 6, alignItems: 'center' }}
                            onClick={() => navigate('/')}
                        >
                            <ListChecks size={14} />
                            Triage
                        </button>
                        <button
                            type="button"
                            className={`btn ${onLibrary ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '6px 10px', fontSize: '0.75rem', display: 'flex', gap: 6, alignItems: 'center' }}
                            onClick={() => navigate('/library')}
                        >
                            <Library size={14} />
                            Library
                        </button>
                    </nav>
                    {title && (
                        <div
                            className="app-title"
                            style={{ marginLeft: 12, fontSize: '1rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}
                        >
                            {title}
                        </div>
                    )}
                </div>

                <div className="flex align-center gap-3">
                    {actions}
                    <button
                        className="btn btn-secondary btn-icon"
                        onClick={toggleTheme}
                        title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
                    >
                        {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
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
        </div>
    );
};

export default AppShell;
