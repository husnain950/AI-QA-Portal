import React from 'react';
import Modal from './Modal';
import { useUiStore } from '../../stores/uiStore';

const SHORTCUT_GROUPS = [
    {
        name: 'Global',
        items: [
            { keys: ['Ctrl', 'K'], label: 'Open command palette' },
            { keys: ['?'], label: 'Show keyboard shortcuts' },
        ],
    },
    {
        name: 'Triage queue',
        items: [
            { keys: ['J', 'K'], label: 'Move down / up the queue' },
            { keys: ['Enter'], label: 'Open finding in review' },
            { keys: ['X'], label: 'Select / deselect finding' },
            { keys: ['A'], label: 'Approve identical variants' },
            { keys: ['F'], label: 'Flag as parse bug' },
            { keys: ['S'], label: 'Skip (this session)' },
            { keys: ['U'], label: 'Undo last change' },
            { keys: ['/'], label: 'Focus detector filter' },
            { keys: ['Esc'], label: 'Clear selection' },
        ],
    },
    {
        name: 'Review workspace',
        items: [
            { keys: ['J', 'K'], label: 'Next / previous section' },
            { keys: ['A'], label: 'Approve section' },
            { keys: ['F'], label: 'Flag section' },
            { keys: ['P'], label: 'Mark section pending' },
            { keys: ['['], label: 'Previous PDF page' },
            { keys: [']'], label: 'Next PDF page' },
            { keys: ['/'], label: 'Focus TOC filter' },
        ],
    },
];

export default function ShortcutsHelp() {
    const open = useUiStore((s) => s.shortcutsHelpOpen);
    const setOpen = useUiStore((s) => s.setShortcutsHelpOpen);

    return (
        <Modal open={open} onClose={() => setOpen(false)} title="Keyboard shortcuts" width={640}>
            <div className="shortcuts-grid">
                {SHORTCUT_GROUPS.map((group) => (
                    <section key={group.name} className="shortcuts-group">
                        <h3>{group.name}</h3>
                        <ul>
                            {group.items.map((item) => (
                                <li key={item.label}>
                                    <span className="shortcuts-keys">
                                        {item.keys.map((k) => <kbd key={k}>{k}</kbd>)}
                                    </span>
                                    <span>{item.label}</span>
                                </li>
                            ))}
                        </ul>
                    </section>
                ))}
            </div>
        </Modal>
    );
}
