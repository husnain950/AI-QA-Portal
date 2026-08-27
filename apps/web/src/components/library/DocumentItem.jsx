import React, { useRef } from 'react';
import { AlertTriangle, Download, Star, Trash2, Upload } from 'lucide-react';
import DropdownMenu from '../ui/DropdownMenu';
import CopyButton from '../ui/CopyButton';
import ProgressBar from '../ui/ProgressBar';
import NewVersionButton from '../review/NewVersionButton';
import DocumentHealth from '../dashboard/DocumentHealth';
import DocumentTags from '../dashboard/DocumentTags';
import { documentLane, laneLabel } from '../../utils/corpusLanes';
import { editionDateFromName } from '../../utils/editions';
import { docCompletion } from '../../utils/libraryQuery';
import { fullDateTime, timeAgo } from '../../utils/time';
import { api } from '../../utils/api';

/** Overflow menu + the hidden NewVersion trigger it drives. Shared by all densities. */
function OverflowActions({ doc, onDelete, onExport, onNewVersion }) {
    const newVersionTrigger = useRef(null);
    return (
        <>
            <NewVersionButton
                documentId={doc.id}
                documentName={doc.name}
                hideButton
                triggerRef={newVersionTrigger}
                onSuccess={onNewVersion}
            />
            <DropdownMenu
                ariaLabel={`Actions for ${doc.name}`}
                items={[
                    { key: 'json', label: 'Export report (JSON)', icon: Download, onSelect: () => onExport(doc.id, 'json') },
                    { key: 'csv', label: 'Export report (CSV)', icon: Download, onSelect: () => onExport(doc.id, 'csv') },
                    {
                        key: 'version',
                        label: 'Upload new JSON version…',
                        icon: Upload,
                        title: 'Add a new JSON version (the PDF stays as it is)',
                        onSelect: () => newVersionTrigger.current?.(),
                    },
                    { type: 'separator' },
                    { key: 'delete', label: 'Delete document…', icon: Trash2, danger: true, onSelect: () => onDelete(doc.id, doc.name) },
                ]}
            />
        </>
    );
}

function FavoriteButton({ doc, isFavorite, onToggleFavorite }) {
    return (
        <button
            type="button"
            className={`btn btn-ghost btn-icon doc-fav ${isFavorite ? 'is-favorite' : ''}`}
            onClick={(event) => {
                event.stopPropagation();
                onToggleFavorite(doc.id);
            }}
            aria-pressed={isFavorite}
            aria-label={isFavorite ? `Remove ${doc.name} from favorites` : `Add ${doc.name} to favorites`}
            title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
        >
            <Star size={14} aria-hidden="true" fill={isFavorite ? 'currentColor' : 'none'} />
        </button>
    );
}

/** Hover-revealed icon actions: favorite, copy link, download PDF. */
function QuickActions({ doc, isFavorite, onToggleFavorite }) {
    return (
        <div className="doc-quick-actions" onClick={(event) => event.stopPropagation()}>
            <FavoriteButton doc={doc} isFavorite={isFavorite} onToggleFavorite={onToggleFavorite} />
            <CopyButton
                getText={() => `${window.location.origin}/review/${doc.id}`}
                title="Copy review link"
                copiedLabel="Link copied"
                size={14}
            />
            <a
                className="btn btn-ghost btn-icon"
                href={api.getFileUrl(doc.pdf_filename)}
                download={doc.pdf_filename}
                title={`Download the source PDF (${doc.pdf_filename})`}
                aria-label={`Download PDF for ${doc.name}`}
                onClick={(event) => event.stopPropagation()}
            >
                <Download size={14} aria-hidden="true" />
            </a>
        </div>
    );
}

function SelectCheckbox({ doc, selected, onToggleSelect }) {
    return (
        <label
            className={`doc-select ${selected ? 'is-selected' : ''}`}
            onClick={(event) => event.stopPropagation()}
            title={selected ? 'Deselect' : 'Select for bulk actions'}
        >
            <input
                type="checkbox"
                checked={selected}
                onChange={() => onToggleSelect(doc.id)}
                aria-label={`Select ${doc.name}`}
            />
        </label>
    );
}

function Badges({ doc, lane, edition }) {
    return (
        <>
            <span className={`source-badge lane-${lane}`}>{laneLabel(lane)}</span>
            {!edition.unknown && (
                <span className="edition-year-badge" title="Edition year">{edition.label}</span>
            )}
            <DocumentTags provenance={doc.provenance} compact />
            {doc.total_sections === 0 && (
                <span
                    className="document-tag tag-provisional"
                    title="The parse produced no sections — re-upload the JSON to fix this document"
                >
                    No sections
                </span>
            )}
        </>
    );
}

function MetaLine({ doc, compact = false }) {
    const flaggedCount = doc.stats?.has_issues || 0;
    return (
        <>
            <span>{doc.total_sections.toLocaleString()} sections</span>
            <span>{doc.total_pages.toLocaleString()} pages</span>
            {!compact && (
                <span title="JSON versions of this parse (the PDF is fixed)">
                    {doc.version_count ?? 1} version{(doc.version_count ?? 1) === 1 ? '' : 's'}
                </span>
            )}
            {flaggedCount > 0 && (
                <span className="doc-row-flagged" title={`${flaggedCount} flagged sections`}>
                    <AlertTriangle size={11} aria-hidden="true" />
                    {flaggedCount} flagged
                </span>
            )}
            {doc.uploaded_at && (
                <span title={`Added ${fullDateTime(doc.uploaded_at)}`}>
                    added {timeAgo(doc.uploaded_at)}
                </span>
            )}
            {doc.last_version_at && doc.last_version_at !== doc.uploaded_at && (
                <span title={`Newest JSON version ${fullDateTime(doc.last_version_at)}`}>
                    updated {timeAgo(doc.last_version_at)}
                </span>
            )}
        </>
    );
}

function useDocDerived(doc) {
    const lane = documentLane(doc);
    const edition = editionDateFromName(doc.name);
    const compPercent = docCompletion(doc);
    return { lane, edition, compPercent };
}

function openOnKeys(event, onOpen) {
    if (event.key === 'Enter') {
        event.preventDefault();
        onOpen();
    }
}

export function DocumentRow({
    doc, selected, onToggleSelect, isFavorite, onToggleFavorite,
    onOpen, onDelete, onExport, onNewVersion, keyboardActive = false,
}) {
    const { lane, edition, compPercent } = useDocDerived(doc);
    return (
        <div
            className={`doc-row ${selected ? 'is-selected' : ''} ${keyboardActive ? 'is-active' : ''}`}
            onClick={onOpen}
            role="link"
            tabIndex={0}
            onKeyDown={(event) => openOnKeys(event, onOpen)}
            data-doc-id={doc.id}
        >
            <SelectCheckbox doc={doc} selected={selected} onToggleSelect={onToggleSelect} />
            <div className="doc-row-main">
                <div className="doc-row-title">
                    <Badges doc={doc} lane={lane} edition={edition} />
                    <h3 className="doc-row-name" title={doc.name}>{doc.name}</h3>
                </div>
                <div className="doc-row-meta">
                    <MetaLine doc={doc} />
                    <DocumentHealth health={doc.health} />
                </div>
            </div>
            <div className="doc-row-progress" title={`${doc.stats?.reviewed || 0} of ${doc.total_sections} sections reviewed`}>
                <ProgressBar pct={compPercent} />
                <span className="doc-row-percent">{compPercent}%</span>
            </div>
            <div className="doc-row-actions" onClick={(event) => event.stopPropagation()}>
                <QuickActions doc={doc} isFavorite={isFavorite} onToggleFavorite={onToggleFavorite} />
                <button className="btn btn-sm btn-secondary" onClick={onOpen}>
                    {compPercent === 0 ? 'Start review' : compPercent === 100 ? 'Open' : 'Continue'}
                </button>
                <OverflowActions doc={doc} onDelete={onDelete} onExport={onExport} onNewVersion={onNewVersion} />
            </div>
        </div>
    );
}

export function DocumentCard({
    doc, selected, onToggleSelect, isFavorite, onToggleFavorite,
    onOpen, onDelete, onExport, onNewVersion, keyboardActive = false,
}) {
    const { lane, edition, compPercent } = useDocDerived(doc);
    return (
        <div
            className={`document-card ${selected ? 'is-selected' : ''} ${keyboardActive ? 'is-active' : ''}`}
            onClick={onOpen}
            role="link"
            tabIndex={0}
            onKeyDown={(event) => openOnKeys(event, onOpen)}
            data-doc-id={doc.id}
        >
            <div className="document-card-head">
                <SelectCheckbox doc={doc} selected={selected} onToggleSelect={onToggleSelect} />
                <Badges doc={doc} lane={lane} edition={edition} />
                <span className="document-card-head-actions" onClick={(event) => event.stopPropagation()}>
                    <FavoriteButton doc={doc} isFavorite={isFavorite} onToggleFavorite={onToggleFavorite} />
                    <OverflowActions doc={doc} onDelete={onDelete} onExport={onExport} onNewVersion={onNewVersion} />
                </span>
            </div>
            <h3 className="document-name" title={doc.name}>{doc.name}</h3>
            <div className="document-card-stats">
                <MetaLine doc={doc} compact />
            </div>
            <DocumentHealth health={doc.health} />
            <div className="document-card-footer">
                <div className="doc-row-progress" title={`${doc.stats?.reviewed || 0} of ${doc.total_sections} sections reviewed`}>
                    <ProgressBar pct={compPercent} />
                    <span className="doc-row-percent">{compPercent}%</span>
                </div>
                <button
                    className="btn btn-sm btn-primary"
                    onClick={(event) => {
                        event.stopPropagation();
                        onOpen();
                    }}
                >
                    {compPercent === 0 ? 'Start review' : compPercent === 100 ? 'Open' : 'Continue'}
                </button>
            </div>
        </div>
    );
}

/** Dense one-line row for scanning large result sets. */
export function DocumentCompactRow({
    doc, selected, onToggleSelect, isFavorite, onToggleFavorite,
    onOpen, onDelete, onExport, onNewVersion, keyboardActive = false,
}) {
    const { lane, edition, compPercent } = useDocDerived(doc);
    const flaggedCount = doc.stats?.has_issues || 0;
    return (
        <div
            className={`doc-compact-row ${selected ? 'is-selected' : ''} ${keyboardActive ? 'is-active' : ''}`}
            onClick={onOpen}
            role="link"
            tabIndex={0}
            onKeyDown={(event) => openOnKeys(event, onOpen)}
            data-doc-id={doc.id}
        >
            <SelectCheckbox doc={doc} selected={selected} onToggleSelect={onToggleSelect} />
            <span onClick={(event) => event.stopPropagation()}>
                <FavoriteButton doc={doc} isFavorite={isFavorite} onToggleFavorite={onToggleFavorite} />
            </span>
            <span className="doc-compact-name" title={doc.name}>
                {doc.name}
                {flaggedCount > 0 && (
                    <span className="doc-row-flagged" title={`${flaggedCount} flagged sections`}>
                        <AlertTriangle size={11} aria-hidden="true" />
                        {flaggedCount}
                    </span>
                )}
            </span>
            <span className={`source-badge lane-${lane}`}>{laneLabel(lane)}</span>
            <span className="doc-compact-cell">{edition.unknown ? '—' : edition.label}</span>
            <span className="doc-compact-cell doc-compact-num" title={`${doc.total_pages} pages`}>
                {doc.total_pages.toLocaleString()}p
            </span>
            <span className="doc-compact-progress" title={`${doc.stats?.reviewed || 0} of ${doc.total_sections} sections reviewed`}>
                <ProgressBar pct={compPercent} ariaHidden />
                <span className="doc-row-percent">{compPercent}%</span>
            </span>
            <span
                className="doc-compact-cell doc-compact-date"
                title={doc.last_version_at ? `Updated ${fullDateTime(doc.last_version_at)}` : `Added ${fullDateTime(doc.uploaded_at)}`}
            >
                {timeAgo(doc.last_version_at || doc.uploaded_at) || '—'}
            </span>
            <span className="doc-compact-actions" onClick={(event) => event.stopPropagation()}>
                <OverflowActions doc={doc} onDelete={onDelete} onExport={onExport} onNewVersion={onNewVersion} />
            </span>
        </div>
    );
}
