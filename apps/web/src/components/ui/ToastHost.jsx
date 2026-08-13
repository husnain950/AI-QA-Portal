import React, { useEffect, useRef, useState } from 'react';
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { useUiStore } from '../../stores/uiStore';

const TOAST_ICONS = {
    success: CheckCircle2,
    error: AlertCircle,
    info: Info,
};

function Toast({ toast, onDismiss }) {
    const [hovered, setHovered] = useState(false);
    const remainingRef = useRef(toast.durationMs ?? 8000);
    const startedAtRef = useRef(Date.now());

    useEffect(() => {
        if (hovered || remainingRef.current <= 0) return undefined;
        startedAtRef.current = Date.now();
        const timer = setTimeout(onDismiss, remainingRef.current);
        return () => {
            clearTimeout(timer);
            remainingRef.current -= Date.now() - startedAtRef.current;
        };
    }, [hovered, onDismiss]);

    const Icon = TOAST_ICONS[toast.type] || Info;

    return (
        <div
            className={`toast toast-${toast.type || 'info'}`}
            role={toast.type === 'error' ? 'alert' : 'status'}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
        >
            <Icon size={15} className="toast-icon" aria-hidden="true" />
            <span className="toast-message">{toast.message}</span>
            {typeof toast.onUndo === 'function' ? (
                <button
                    type="button"
                    className="btn btn-xs btn-secondary toast-undo"
                    onClick={() => {
                        toast.onUndo();
                        onDismiss();
                    }}
                >
                    Undo
                </button>
            ) : null}
            <button
                type="button"
                className="toast-dismiss"
                aria-label="Dismiss notification"
                onClick={onDismiss}
            >
                <X size={14} />
            </button>
        </div>
    );
}

export default function ToastHost() {
    const toasts = useUiStore((s) => s.toasts);
    const dismissToast = useUiStore((s) => s.dismissToast);

    if (!toasts.length) return null;

    return (
        <div className="toast-host" aria-live="polite">
            {toasts.map((t) => (
                <Toast key={t.id} toast={t} onDismiss={() => dismissToast(t.id)} />
            ))}
        </div>
    );
}
