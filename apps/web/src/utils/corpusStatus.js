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

    // `corpora` is the registry-driven list the API returns, one entry per corpus.
    // The two flat booleans are the pre-registry shape and are kept as a fallback so a
    // frontend deployed against an older API still reports something truthful.
    const mounts = Array.isArray(status?.corpora) && status.corpora.length
        ? status.corpora.map((c) => ({
            label: c.label,
            title: c.title || c.label,
            mounted: Boolean(c.configured),
        }))
        : [
            { label: 'ordinance', title: 'Ordinance', mounted: Boolean(status?.ordinance_configured) },
            { label: 'acts', title: 'Acts', mounted: Boolean(status?.acts_configured) },
        ];

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

    const anyMounted = mounts.some((m) => m.mounted);
    const mountsLabel = anyMounted
        ? mounts
            .map((m) => `${m.title} ${m.mounted ? 'mounted' : 'not on this host'}`)
            .join(' / ')
        : 'pipeline mounts not on this host';

    return {
        syncKind,
        syncLabel,
        lastSyncAt,
        lastStatus,
        mounts,
        mountsLabel,
        canSync: anyMounted,
        // Named accessors the dashboard and its tests already use.
        ordinanceMounted: Boolean(mounts.find((m) => m.label === 'ordinance')?.mounted),
        actsMounted: Boolean(mounts.find((m) => m.label === 'acts')?.mounted),
        rulesMounted: Boolean(mounts.find((m) => m.label === 'rules')?.mounted),
    };
}
