import React from 'react';
import { Download, Star, Trash2, X } from 'lucide-react';

/** Floating bulk-action bar shown while a selection exists. */
export default function SelectionBar({
    count,
    loadedCount,
    onSelectAllLoaded,
    onFavorite,
    onExportCsv,
    onDelete,
    onClear,
}) {
    if (!count) return null;
    return (
        <div className="selection-bar" role="toolbar" aria-label={`${count} documents selected`}>
            <span className="selection-bar-count">
                <strong>{count}</strong> selected
            </span>
            {count < loadedCount && (
                <button type="button" className="btn btn-sm btn-ghost" onClick={onSelectAllLoaded}>
                    Select all {loadedCount.toLocaleString()} loaded
                </button>
            )}
            <button type="button" className="btn btn-sm btn-ghost" onClick={onFavorite}>
                <Star size={14} aria-hidden="true" />
                <span>Favorite</span>
            </button>
            <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={onExportCsv}
                title="Download a metadata manifest of the selection (name, lane, pages, progress, dates)"
            >
                <Download size={14} aria-hidden="true" />
                <span>Export CSV</span>
            </button>
            <button type="button" className="btn btn-sm btn-ghost selection-bar-danger" onClick={onDelete}>
                <Trash2 size={14} aria-hidden="true" />
                <span>Delete…</span>
            </button>
            <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={onClear}
                title="Clear selection (Esc)"
            >
                <X size={14} aria-hidden="true" />
            </button>
        </div>
    );
}
