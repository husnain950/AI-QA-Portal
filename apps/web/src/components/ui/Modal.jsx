import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * Shared modal built on native <dialog> — focus trap, Escape and backdrop
 * click for free. Children render inside a scrollable body.
 */
export default function Modal({
    open,
    onClose,
    title,
    children,
    footer = null,
    width = 560,
    className = '',
    closeOnBackdrop = true,
}) {
    const ref = useRef(null);
    const titleId = useId();

    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        if (open && !el.open) el.showModal();
        else if (!open && el.open) el.close();
    }, [open]);

    return (
        <dialog
            ref={ref}
            className={`ui-modal ${className}`}
            style={{ width: `min(${width}px, 94vw)` }}
            aria-labelledby={title ? titleId : undefined}
            onCancel={(e) => {
                e.preventDefault();
                onClose?.();
            }}
            onClick={(e) => {
                if (closeOnBackdrop && e.target === ref.current) onClose?.();
            }}
        >
            {open ? (
                <div className="ui-modal-inner">
                    <header className="ui-modal-header">
                        {title ? <h2 id={titleId} className="ui-modal-title">{title}</h2> : <span />}
                        <button
                            type="button"
                            className="btn btn-ghost btn-icon"
                            aria-label="Close dialog"
                            onClick={() => onClose?.()}
                        >
                            <X size={16} />
                        </button>
                    </header>
                    <div className="ui-modal-body">{children}</div>
                    {footer ? <footer className="ui-modal-footer">{footer}</footer> : null}
                </div>
            ) : null}
        </dialog>
    );
}
