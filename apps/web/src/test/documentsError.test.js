import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../utils/api';
import { useDocumentStore } from '../stores/documentStore';

describe('fetchDocuments error state', () => {
    beforeEach(() => {
        useDocumentStore.setState({ documents: [], documentsError: null });
        vi.restoreAllMocks();
    });

    it('records the failure so an empty list is not read as an empty corpus', async () => {
        vi.spyOn(api, 'get').mockRejectedValue(new Error('API request failed'));
        vi.spyOn(console, 'error').mockImplementation(() => {});

        await useDocumentStore.getState().fetchDocuments();

        expect(useDocumentStore.getState().documents).toEqual([]);
        expect(useDocumentStore.getState().documentsError).toBe('API request failed');
        expect(useDocumentStore.getState().loading.documents).toBe(false);
    });

    it('clears the error once a retry succeeds', async () => {
        useDocumentStore.setState({ documentsError: 'API request failed' });
        vi.spyOn(api, 'get').mockResolvedValue([{ id: 'a', name: 'Act' }]);

        await useDocumentStore.getState().fetchDocuments();

        expect(useDocumentStore.getState().documents).toHaveLength(1);
        expect(useDocumentStore.getState().documentsError).toBeNull();
    });
});

describe('api.get transient retry', () => {
    beforeEach(() => vi.restoreAllMocks());

    it('retries a 502 once and returns the second response', async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({}) })
            .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [{ id: 'a' }] });
        vi.stubGlobal('fetch', fetchMock);

        const pending = api.get('/documents');
        await vi.advanceTimersByTimeAsync(1500);
        await expect(pending).resolves.toEqual([{ id: 'a' }]);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        vi.useRealTimers();
    });

    it('does not retry a 404', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: false, status: 404, json: async () => ({ detail: 'Document not found' }),
        });
        vi.stubGlobal('fetch', fetchMock);

        await expect(api.get('/documents/nope')).rejects.toThrow('Document not found');
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});
