import React from 'react';
import { Bookmark, Trash2 } from 'lucide-react';
import DropdownMenu from '../ui/DropdownMenu';
import { useUiStore } from '../../stores/uiStore';
import { useSavedViews } from '../../utils/savedViews';

export default function SavedViewsMenu({ currentSearch, hasActiveState, onApply }) {
    const views = useSavedViews((state) => state.views);
    const saveView = useSavedViews((state) => state.save);
    const removeView = useSavedViews((state) => state.remove);
    const promptDialog = useUiStore((state) => state.promptDialog);
    const pushToast = useUiStore((state) => state.pushToast);

    const saveCurrent = async () => {
        const name = await promptDialog({
            title: 'Save current view',
            message: 'Saves the current search, filters, sort, and view under a name on this browser.',
            defaultValue: '',
            confirmLabel: 'Save view',
        });
        const trimmed = (name || '').trim();
        if (!trimmed) return;
        saveView(trimmed, currentSearch || '');
        pushToast({ type: 'success', message: `Saved view "${trimmed}"` });
    };

    const items = [
        ...views.map((view) => ({
            key: `apply:${view.name}`,
            label: view.name,
            icon: Bookmark,
            title: view.search ? `?${view.search}` : 'Unfiltered library',
            onSelect: () => onApply(view.search),
        })),
        ...(views.length ? [{ type: 'separator' }] : []),
        {
            key: 'save',
            label: 'Save current view…',
            icon: Bookmark,
            disabled: !hasActiveState,
            title: hasActiveState ? undefined : 'Nothing to save — the library is unfiltered',
            onSelect: saveCurrent,
        },
        ...(views.length
            ? [
                { type: 'separator' },
                { type: 'header', label: 'Delete saved view' },
                ...views.map((view) => ({
                    key: `delete:${view.name}`,
                    label: view.name,
                    icon: Trash2,
                    danger: true,
                    onSelect: () => removeView(view.name),
                })),
            ]
            : []),
    ];

    return (
        <DropdownMenu
            ariaLabel="Saved views"
            align="end"
            buttonClassName="library-icon-toggle"
            buttonContent={<Bookmark size={15} aria-hidden="true" />}
            items={items}
        />
    );
}
