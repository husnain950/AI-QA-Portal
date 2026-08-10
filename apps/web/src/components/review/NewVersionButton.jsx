import React, { useRef, useState } from 'react';
import { Upload, Loader2 } from 'lucide-react';
import { versionsApi } from '../../utils/api';
import { useUiStore } from '../../stores/uiStore';

/**
 * Shared "New JSON version" control used by ReviewPage and DashboardPage.
 */
export default function NewVersionButton({
    documentId,
    documentName = '',
    onSuccess,
    className = 'btn btn-secondary',
    style,
    label = 'New JSON version',
}) {
    const inputRef = useRef(null);
    const [loading, setLoading] = useState(false);
    const pushToast = useUiStore((s) => s.pushToast);
    const promptDialog = useUiStore((s) => s.promptDialog);

    const onFile = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        if (!file.name.endsWith('.json')) {
            pushToast({ type: 'error', message: 'Please select a valid JSON file.' });
            e.target.value = '';
            return;
        }

        const nameBit = documentName ? ` of "${documentName}"` : '';
        const note = await promptDialog({
            title: 'New JSON version',
            message:
                `Add this JSON as a new version${nameBit}?\n\n`
                + 'The PDF is untouched. Stable leaves keep their QA state; '
                + 'findings on changed leaves are re-anchored.\n\n'
                + 'Optional note (what did the pipeline fix?):',
            defaultValue: '',
            confirmLabel: 'Create version',
        });
        if (note === null) {
            e.target.value = '';
            return;
        }

        try {
            setLoading(true);
            await versionsApi.create(documentId, file, { note: note || '' });
            if (onSuccess) await onSuccess({ note });
        } catch (err) {
            pushToast({
                type: 'error',
                message: `Failed to replace JSON: ${err.message || 'Unknown error'}`,
            });
        } finally {
            setLoading(false);
            e.target.value = '';
        }
    };

    return (
        <>
            <input
                ref={inputRef}
                type="file"
                accept=".json,application/json"
                style={{ display: 'none' }}
                onChange={onFile}
            />
            <button
                type="button"
                className={className}
                style={style}
                disabled={loading || !documentId}
                onClick={() => inputRef.current?.click()}
                title="Add a new JSON version for this document (the PDF stays as it is)"
            >
                {loading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                <span>{label}</span>
            </button>
        </>
    );
}
