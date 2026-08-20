import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * Right-side drawer panel. Closes on Escape; focuses itself on open so
 * keyboard users land inside. Non-modal: the page behind stays interactive.
 */
export default function Drawer({
    open,
    onClose,
    title,
    icon = null,
    children,
    width = 460,
    className = '',
    headerExtra = null,
}) {
    const ref = useRef(null);
    const restoreFocusRef = useRef(null);

    useEffect(() => {
        if (!open) return undefined;
        restoreFocusRef.current = document.activeElement;
        ref.current?.focus();
        const onKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onClose?.();
                return;
            }
            if (e.key === 'Tab') {
                const focusable = [...(ref.current?.querySelectorAll(
                    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
                ) || [])];
                if (!focusable.length) {
                    e.preventDefault();
                    ref.current?.focus();
                    return;
                }
                const first = focusable[0];
                const last = focusable.at(-1);
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        };
        const el = ref.current;
        el?.addEventListener('keydown', onKey);
        return () => {
            el?.removeEventListener('keydown', onKey);
            restoreFocusRef.current?.focus?.();
        };
    }, [open, onClose]);

    if (!open) return null;

    return (
        <aside
            ref={ref}
            className={`ui-drawer ${className}`}
            style={{ width: `min(${width}px, 100vw)` }}
            role="dialog"
            aria-label={typeof title === 'string' ? title : undefined}
            tabIndex={-1}
        >
            <header className="ui-drawer-header">
                <h3 className="ui-drawer-title">
                    {icon}
                    {title}
                </h3>
                {headerExtra}
                <button
                    type="button"
                    className="btn btn-ghost btn-icon"
                    aria-label="Close panel"
                    onClick={() => onClose?.()}
                    title="Close (Esc)"
                >
                    <X size={16} />
                </button>
            </header>
            <div className="ui-drawer-body">{children}</div>
        </aside>
    );
}
