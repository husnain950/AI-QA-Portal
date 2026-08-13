import React, { useEffect, useRef, useState } from 'react';
import { MoreHorizontal } from 'lucide-react';

/**
 * Overflow action menu. items: [{ key, label, icon, onSelect, danger, disabled, title }]
 * or { type: 'separator' }. Closes on outside click, Escape and selection.
 */
export default function DropdownMenu({
    items,
    ariaLabel = 'More actions',
    buttonClassName = 'btn btn-ghost btn-icon',
    buttonContent = <MoreHorizontal size={16} />,
    align = 'end',
}) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef(null);
    const menuRef = useRef(null);

    useEffect(() => {
        if (!open) return undefined;
        const onPointerDown = (e) => {
            if (!rootRef.current?.contains(e.target)) setOpen(false);
        };
        const onKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                setOpen(false);
                return;
            }
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                const focusables = [...(menuRef.current?.querySelectorAll('button:not(:disabled)') || [])];
                if (!focusables.length) return;
                const idx = focusables.indexOf(document.activeElement);
                const next = e.key === 'ArrowDown'
                    ? focusables[(idx + 1) % focusables.length]
                    : focusables[(idx - 1 + focusables.length) % focusables.length];
                next?.focus();
            }
        };
        document.addEventListener('pointerdown', onPointerDown);
        document.addEventListener('keydown', onKey);
        queueMicrotask(() => menuRef.current?.querySelector('button:not(:disabled)')?.focus());
        return () => {
            document.removeEventListener('pointerdown', onPointerDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    return (
        <div className="ui-dropdown" ref={rootRef}>
            <button
                type="button"
                className={buttonClassName}
                aria-label={ariaLabel}
                aria-haspopup="menu"
                aria-expanded={open}
                title={ariaLabel}
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
            >
                {buttonContent}
            </button>
            {open ? (
                <div className={`ui-dropdown-menu align-${align}`} role="menu" ref={menuRef}>
                    {items.map((item, i) => {
                        if (item.type === 'separator') {
                            return <div key={`sep-${i}`} className="ui-dropdown-separator" role="separator" />;
                        }
                        const Icon = item.icon;
                        return (
                            <button
                                key={item.key || item.label}
                                type="button"
                                role="menuitem"
                                className={`ui-dropdown-item ${item.danger ? 'is-danger' : ''}`}
                                disabled={item.disabled}
                                title={item.title || undefined}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setOpen(false);
                                    item.onSelect?.();
                                }}
                            >
                                {Icon ? <Icon size={14} aria-hidden="true" /> : null}
                                <span>{item.label}</span>
                            </button>
                        );
                    })}
                </div>
            ) : null}
        </div>
    );
}
