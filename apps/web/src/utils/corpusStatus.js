/**
 * Library subtitle for pipeline-mount health — not document count.
 *
 * Ordinance / Acts here are the gitignored corpus directories on the API host
 * (`CORPUS_ORDINANCE` / `CORPUS_ACTS`: PDFs + `output/*.json`). They are not
 * the Library Source facets, and `ordinance_configured` is unrelated to how
 * many Ordinance documents are already in SQLite.
 */

export const CORPUS_MOUNT_HINT =
    'Ordinance and Acts here are pipeline corpus directories on the API host (PDFs + output JSON), not the documents listed below.';

export function describeCorpusSync(status) {
    const total = Number(status?.total_documents) || 0;
    const lastSyncAt = status?.last_sync_at || null;
    const lastStatus = status?.last_status || null;
    const ordinanceMounted = Boolean(status?.ordinance_configured);
    const actsMounted = Boolean(status?.acts_configured);

    let syncKind;
    let syncLabel;
    if (lastSyncAt) {
        syncKind = 'recorded';
        syncLabel = null;
    } else if (total > 0) {
        syncKind = 'upload';
        syncLabel = 'seeded by upload';
    } else {
        syncKind = 'never';
        syncLabel = 'never synced';
    }

    const mountsLabel = (!ordinanceMounted && !actsMounted)
        ? 'pipeline mounts not on this host'
        : `Ordinance ${ordinanceMounted ? 'mounted' : 'not on this host'} / Acts ${actsMounted ? 'mounted' : 'not on this host'}`;

    return {
        syncKind,
        syncLabel,
        lastSyncAt,
        lastStatus,
        mountsLabel,
        canSync: ordinanceMounted || actsMounted,
        ordinanceMounted,
        actsMounted,
    };
}
