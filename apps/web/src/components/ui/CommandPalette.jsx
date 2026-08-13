import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    FileText, Library, ListChecks, UploadCloud, Moon, Sun, RefreshCw, User, Keyboard, CornerDownLeft,
} from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';
import { useDocumentStore } from '../../stores/documentStore';
import { corpusApi } from '../../utils/api';
import { editionDateFromName } from '../../utils/editions';
import { laneLabel } from '../../utils/corpusLanes';

function matches(query, ...haystacks) {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const text = haystacks.filter(Boolean).join(' ').toLowerCase();
    // Every whitespace-separated term must appear somewhere.
    return q.split(/\s+/).every((term) => text.includes(term));
}

export default function CommandPalette() {
    const navigate = useNavigate();
    const open = useUiStore((s) => s.commandPaletteOpen);
    const setOpen = useUiStore((s) => s.setCommandPaletteOpen);
    const toggleTheme = useUiStore((s) => s.toggleTheme);
    const theme = useUiStore((s) => s.theme);
    const setShortcutsHelpOpen = useUiStore((s) => s.setShortcutsHelpOpen);
    const pushToast = useUiStore((s) => s.pushToast);
    const promptDialog = useUiStore((s) => s.promptDialog);
    const setReviewer = useUiStore((s) => s.setReviewer);
    const reviewerName = useUiStore((s) => s.reviewerName);

    const documents = useDocumentStore((s) => s.documents);
    const fetchDocuments = useDocumentStore((s) => s.fetchDocuments);

    const [query, setQuery] = useState('');
    const [cursor, setCursor] = useState(0);
    const inputRef = useRef(null);
    const listRef = useRef(null);

    useEffect(() => {
        if (!open) return;
        setQuery('');
        setCursor(0);
        queueMicrotask(() => inputRef.current?.focus());
        if (!documents.length) fetchDocuments();
    }, [open, documents.length, fetchDocuments]);

    const close = () => setOpen(false);

    const run = (fn) => {
        close();
        fn();
    };

    const commands = useMemo(() => {
        const nav = [
            { key: 'nav-triage', group: 'Navigate', label: 'Go to Triage', icon: ListChecks, keywords: 'queue findings home', action: () => navigate('/') },
            { key: 'nav-library', group: 'Navigate', label: 'Go to Library', icon: Library, keywords: 'documents dashboard corpus', action: () => navigate('/library') },
            { key: 'nav-upload', group: 'Navigate', label: 'Go to Upload', icon: UploadCloud, keywords: 'new document pdf json', action: () => navigate('/upload') },
        ];
        const actions = [
            {
                key: 'act-theme',
                group: 'Actions',
                label: theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode',
                icon: theme === 'light' ? Moon : Sun,
                keywords: 'theme appearance',
                action: () => toggleTheme(),
            },
            {
                key: 'act-sync',
                group: 'Actions',
                label: 'Sync corpus',
                icon: RefreshCw,
                keywords: 'refresh import ordinance acts',
                action: async () => {
                    pushToast({ type: 'info', message: 'Corpus sync started…' });
                    try {
                        const summary = await corpusApi.sync({ metrics: true });
                        const ord = summary.ordinance || {};
                        const acts = summary.acts || {};
                        pushToast({
                            type: 'success',
                            message: `Sync finished — Ordinance ${ord.imported ?? 0} imported, Acts ${acts.imported ?? 0} imported.`,
                        });
                    } catch (err) {
                        pushToast({ type: 'error', message: `Corpus sync failed: ${err.message || 'Unknown error'}` });
                    }
                },
            },
            {
                key: 'act-reviewer',
                group: 'Actions',
                label: 'Change reviewer name',
                icon: User,
                keywords: 'identity attribution rename',
                action: async () => {
                    const value = await promptDialog({
                        title: 'Reviewer name',
                        message: 'Shown on review events and notes (attribution only, not authentication).',
                        defaultValue: reviewerName === 'anonymous' ? '' : reviewerName,
                        confirmLabel: 'Save',
                    });
                    if (value !== null && value !== undefined) setReviewer(value);
                },
            },
            {
                key: 'act-shortcuts',
                group: 'Actions',
                label: 'Keyboard shortcuts',
                icon: Keyboard,
                keywords: 'help keys bindings',
                action: () => setShortcutsHelpOpen(true),
            },
        ];
        const docs = documents.map((doc) => {
            const edition = editionDateFromName(doc.name);
            const lane = doc.corpus_lane || (doc.source_type === 'acts_corpus' ? 'other_acts' : 'manual');
            return {
                key: `doc-${doc.id}`,
                group: 'Open document',
                label: doc.name,
                sublabel: `${laneLabel(lane)}${edition.unknown ? '' : ` · ${edition.label}`}`,
                icon: FileText,
                keywords: laneLabel(lane),
                action: () => navigate(`/review/${doc.id}`),
            };
        });
        return [...nav, ...actions, ...docs];
    }, [documents, navigate, theme, toggleTheme, pushToast, promptDialog, setReviewer, reviewerName, setShortcutsHelpOpen]);

    const filtered = useMemo(
        () => commands.filter((c) => matches(query, c.label, c.sublabel, c.keywords, c.group)),
        [commands, query],
    );

    useEffect(() => {
        if (cursor >= filtered.length) setCursor(Math.max(0, filtered.length - 1));
    }, [filtered.length, cursor]);

    useEffect(() => {
        listRef.current
            ?.querySelector('.cp-item.active')
            ?.scrollIntoView({ block: 'nearest' });
    }, [cursor]);

    if (!open) return null;

    const groups = [];
    for (const cmd of filtered) {
        const last = groups[groups.length - 1];
        if (!last || last.name !== cmd.group) groups.push({ name: cmd.group, items: [cmd] });
        else last.items.push(cmd);
    }

    const onKeyDown = (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            close();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setCursor((c) => Math.min(c + 1, filtered.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setCursor((c) => Math.max(0, c - 1));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const cmd = filtered[cursor];
            if (cmd) run(cmd.action);
        }
    };

    return (
        <div className="cp-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
            <div className="cp-panel" role="dialog" aria-modal="true" aria-label="Command palette">
                <div className="cp-input-row">
                    <input
                        ref={inputRef}
                        className="cp-input"
                        placeholder="Search documents, pages and actions…"
                        value={query}
                        onChange={(e) => {
                            setQuery(e.target.value);
                            setCursor(0);
                        }}
                        onKeyDown={onKeyDown}
                        aria-label="Search commands"
                    />
                    <kbd>Esc</kbd>
                </div>
                <div className="cp-list" ref={listRef} role="listbox" aria-label="Commands">
                    {filtered.length === 0 ? (
                        <div className="cp-empty">No matches for “{query}”.</div>
                    ) : (
                        groups.map((group) => (
                            <div key={group.name} className="cp-group">
                                <div className="cp-group-label">{group.name}</div>
                                {group.items.map((cmd) => {
                                    const idx = filtered.indexOf(cmd);
                                    const Icon = cmd.icon;
                                    return (
                                        <button
                                            key={cmd.key}
                                            type="button"
                                            role="option"
                                            aria-selected={idx === cursor}
                                            className={`cp-item ${idx === cursor ? 'active' : ''}`}
                                            onMouseEnter={() => setCursor(idx)}
                                            onClick={() => run(cmd.action)}
                                        >
                                            {Icon ? <Icon size={15} aria-hidden="true" /> : null}
                                            <span className="cp-item-label">{cmd.label}</span>
                                            {cmd.sublabel ? <span className="cp-item-sub">{cmd.sublabel}</span> : null}
                                            {idx === cursor ? <CornerDownLeft size={13} className="cp-item-enter" aria-hidden="true" /> : null}
                                        </button>
                                    );
                                })}
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
