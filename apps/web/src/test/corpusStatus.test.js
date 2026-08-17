import { describe, expect, it } from 'vitest';
import { describeCorpusSync } from '../utils/corpusStatus';

describe('describeCorpusSync', () => {
    it('says seeded by upload when documents exist but no pipeline sync ran', () => {
        const meta = describeCorpusSync({
            last_sync_at: null,
            last_status: null,
            ordinance_configured: false,
            acts_configured: false,
            total_documents: 88,
        });
        expect(meta.syncKind).toBe('upload');
        expect(meta.syncLabel).toBe('seeded by upload');
        expect(meta.mountsLabel).toBe('pipeline mounts not on this host');
        expect(meta.canSync).toBe(false);
    });

    it('says never synced when the library is empty and mounts are absent', () => {
        const meta = describeCorpusSync({
            last_sync_at: null,
            ordinance_configured: false,
            acts_configured: false,
            total_documents: 0,
        });
        expect(meta.syncKind).toBe('never');
        expect(meta.syncLabel).toBe('never synced');
        expect(meta.mountsLabel).toBe('pipeline mounts not on this host');
    });

    it('keeps last-sync copy when corpus_sync_state has a timestamp', () => {
        const meta = describeCorpusSync({
            last_sync_at: '2026-08-13T13:00:00Z',
            last_status: 'ok',
            ordinance_configured: true,
            acts_configured: true,
            total_documents: 90,
        });
        expect(meta.syncKind).toBe('recorded');
        expect(meta.lastStatus).toBe('ok');
        expect(meta.mountsLabel).toBe('Ordinance mounted / Acts mounted');
        expect(meta.canSync).toBe(true);
    });

    it('names a single missing mount without calling it document-missing', () => {
        const meta = describeCorpusSync({
            last_sync_at: null,
            ordinance_configured: true,
            acts_configured: false,
            total_documents: 0,
        });
        expect(meta.syncLabel).toBe('never synced');
        expect(meta.mountsLabel).toBe('Ordinance mounted / Acts not on this host');
        expect(meta.canSync).toBe(true);
    });
});
