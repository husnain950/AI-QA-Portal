import React from 'react';
import { useUiStore } from '../../stores/uiStore';

export default function ToastHost() {
    const toasts = useUiStore((s) => s.toasts);
    const dismissToast = useUiStore((s) => s.dismissToast);

    if (!toasts.length) return null;

    return (
        <div className="toast-host" aria-live="polite">
            {toasts.map((t) => (
                <div key={t.id} className={`toast toast-${t.type || 'info'}`}>
                    <span className="toast-message">{t.message}</span>
                    {typeof t.onUndo === 'function' ? (
                        <button
                            type="button"
                            className="toast-undo"
                            onClick={() => {
                                t.onUndo();
                                dismissToast(t.id);
                            }}
                        >
                            Undo
                        </button>
                    ) : null}
                    <button
                        type="button"
                        className="toast-dismiss"
                        aria-label="Dismiss"
                        onClick={() => dismissToast(t.id)}
                    >
                        ×
                    </button>
                </div>
            ))}
        </div>
    );
}
