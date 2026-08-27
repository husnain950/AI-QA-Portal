/** Client-side metadata CSV for a selection of loaded documents — distinct from
 * the per-document QA report export (server-side), this one is a quick manifest
 * of whatever the reviewer has selected in the Library. */
import { documentLane, laneLabel } from './corpusLanes';
import { editionDateFromName } from './editions';
import { docCompletion } from './libraryQuery';

const COLUMNS = [
    ['name', (doc) => doc.name],
    ['lane', (doc) => laneLabel(documentLane(doc))],
    ['edition_year', (doc) => editionDateFromName(doc.name).label],
    ['pages', (doc) => doc.total_pages],
    ['sections', (doc) => doc.total_sections],
    ['reviewed_percent', (doc) => docCompletion(doc)],
    ['flagged_sections', (doc) => doc.stats?.has_issues || 0],
    ['open_annotations', (doc) => doc.stats?.open_annotations || 0],
    ['versions', (doc) => doc.version_count ?? 1],
    ['added_at', (doc) => doc.uploaded_at || ''],
    ['updated_at', (doc) => doc.last_version_at || ''],
    ['pdf_filename', (doc) => doc.pdf_filename],
];

function csvCell(value) {
    const text = String(value ?? '');
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function exportDocumentsCsv(docs) {
    const header = COLUMNS.map(([key]) => key).join(',');
    const rows = docs.map((doc) => COLUMNS.map(([, cell]) => csvCell(cell(doc))).join(','));
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `library-selection-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}
