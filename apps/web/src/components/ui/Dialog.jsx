import React, { useEffect, useId, useRef, useState } from 'react';
import { useUiStore } from '../../stores/uiStore';

/** Native <dialog>-based modal with focus trap via showModal(). */
export default function DialogHost() {
    const dialogState = useUiStore((s) => s.dialog);
    const closeDialog = useUiStore((s) => s.closeDialog);
    const ref = useRef(null);
    const inputRef = useRef(null);
    const titleId = useId();
    const [promptValue, setPromptValue] = useState('');

    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        if (dialogState) {
            setPromptValue(dialogState.defaultValue || '');
            if (!el.open) el.showModal();
            if (dialogState.prompt) {
                queueMicrotask(() => inputRef.current?.focus());
            }
        } else if (el.open) {
            el.close();
        }
    }, [dialogState]);

    if (!dialogState) {
        return <dialog ref={ref} className="ui-dialog" aria-hidden="true" />;
    }

    const onCancel = (e) => {
        e.preventDefault();
        closeDialog(dialogState.prompt ? null : false);
    };

    const onConfirm = () => {
        if (dialogState.prompt) {
            closeDialog(promptValue);
        } else {
            closeDialog(true);
        }
    };

    return (
        <dialog
            ref={ref}
            className="ui-dialog"
            aria-labelledby={titleId}
            onCancel={onCancel}
            onClick={(e) => {
                if (e.target === ref.current) onCancel(e);
            }}
        >
            <form
                method="dialog"
                className="ui-dialog-body"
                onSubmit={(e) => {
                    e.preventDefault();
                    onConfirm();
                }}
            >
                {dialogState.title ? (
                    <h2 id={titleId} className="ui-dialog-title">{dialogState.title}</h2>
                ) : null}
                {dialogState.message ? (
                    <p className="ui-dialog-message">{dialogState.message}</p>
                ) : null}
                {dialogState.prompt ? (
                    <input
                        ref={inputRef}
                        className="ui-dialog-input"
                        value={promptValue}
                        onChange={(e) => setPromptValue(e.target.value)}
                    />
                ) : null}
                <div className="ui-dialog-actions">
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => closeDialog(dialogState.prompt ? null : false)}
                    >
                        {dialogState.cancelLabel || 'Cancel'}
                    </button>
                    <button type="submit" className="btn btn-primary">
                        {dialogState.confirmLabel || 'OK'}
                    </button>
                </div>
            </form>
        </dialog>
    );
}
