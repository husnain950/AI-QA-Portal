import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, ApiError } from '../utils/api';

const OK = { email: 'admin@crx.test', role: 'admin' };

function jsonResponse(body, status = 200) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

describe('api.post retry', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('retries a login POST once after a timeout when asked', async () => {
        const fetchMock = vi.fn()
            .mockRejectedValueOnce(new TypeError('Failed to fetch'))
            .mockResolvedValueOnce(jsonResponse(OK));
        vi.stubGlobal('fetch', fetchMock);

        const pending = api.post('/auth/login', { email: 'a', password: 'b' }, false, { retry: true });
        await vi.advanceTimersByTimeAsync(800);
        await expect(pending).resolves.toEqual(OK);
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('retries a login POST once after a 503', async () => {
        const fetchMock = vi.fn()
            .mockResolvedValueOnce(jsonResponse({
                code: 'database_unreachable',
                detail: { code: 'database_unreachable', message: 'the database is not reachable' },
            }, 503))
            .mockResolvedValueOnce(jsonResponse(OK));
        vi.stubGlobal('fetch', fetchMock);

        const pending = api.post('/auth/login', { email: 'a', password: 'b' }, false, { retry: true });
        await vi.advanceTimersByTimeAsync(800);
        await expect(pending).resolves.toEqual(OK);
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('does not retry POST by default', async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
        vi.stubGlobal('fetch', fetchMock);

        await expect(api.post('/auth/logout', {})).rejects.toBeInstanceOf(ApiError);
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});
