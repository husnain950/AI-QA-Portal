import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getDocumentMock } = vi.hoisted(() => ({
    getDocumentMock: vi.fn(),
}));

vi.mock('pdfjs-dist', () => ({
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: getDocumentMock,
}));

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs', () => ({
    WorkerMessageHandler: {},
}));

import { usePdfDocument } from '../hooks/usePdfRenderer';

const deferred = () => {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
};

describe('usePdfDocument', () => {
    beforeEach(() => {
        getDocumentMock.mockReset();
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('sets an explicit error and clears loading when pdfUrl is missing', async () => {
        const { result } = renderHook(() => usePdfDocument(null));

        await waitFor(() => {
            expect(result.current.loading).toBe(false);
            expect(result.current.error?.message).toMatch(/no pdf url/i);
        });
        expect(getDocumentMock).not.toHaveBeenCalled();
        expect(result.current.pdfDoc).toBeNull();
    });

    it('surfaces load rejections as errors without leaving the spinner on', async () => {
        const loading = deferred();
        const destroy = vi.fn();
        getDocumentMock.mockReturnValue({ promise: loading.promise, destroy });

        const { result } = renderHook(() => usePdfDocument('/uploads/broken.pdf'));

        await waitFor(() => expect(result.current.loading).toBe(true));

        await act(async () => {
            loading.reject(new Error('HTTP 404'));
        });

        await waitFor(() => {
            expect(result.current.loading).toBe(false);
            expect(result.current.error?.message).toBe('HTTP 404');
        });
        expect(result.current.pdfDoc).toBeNull();
    });

    it('times out hung loads and clears the spinner', async () => {
        const loading = deferred();
        const destroy = vi.fn();
        getDocumentMock.mockReturnValue({ promise: loading.promise, destroy });

        const { result } = renderHook(() =>
            usePdfDocument('/uploads/hang.pdf', { timeoutMs: 1_000 }),
        );

        await waitFor(() => expect(result.current.loading).toBe(true));

        await act(async () => {
            await vi.advanceTimersByTimeAsync(1_000);
        });

        await waitFor(() => {
            expect(result.current.loading).toBe(false);
            expect(result.current.error?.message).toMatch(/timed out/i);
        });
        expect(destroy).toHaveBeenCalled();
        expect(result.current.pdfDoc).toBeNull();
    });

    it('retry re-invokes getDocument after a failure', async () => {
        const first = deferred();
        const second = deferred();
        const destroy = vi.fn();
        getDocumentMock
            .mockReturnValueOnce({ promise: first.promise, destroy })
            .mockReturnValueOnce({
                promise: second.promise,
                destroy,
            });

        const { result } = renderHook(() => usePdfDocument('/uploads/retry.pdf'));

        await act(async () => {
            first.reject(new Error('network'));
        });
        await waitFor(() => expect(result.current.error?.message).toBe('network'));

        await act(async () => {
            result.current.retry();
        });

        await waitFor(() => expect(getDocumentMock).toHaveBeenCalledTimes(2));

        await act(async () => {
            second.resolve({ numPages: 3, destroy: vi.fn() });
        });

        await waitFor(() => {
            expect(result.current.loading).toBe(false);
            expect(result.current.error).toBeNull();
            expect(result.current.numPages).toBe(3);
        });
    });

    it('destroys in-flight loading tasks on unmount / url change', async () => {
        const loading = deferred();
        const destroy = vi.fn();
        getDocumentMock.mockReturnValue({ promise: loading.promise, destroy });

        const { unmount } = renderHook(() => usePdfDocument('/uploads/cancel.pdf'));
        await waitFor(() => expect(getDocumentMock).toHaveBeenCalled());

        unmount();
        expect(destroy).toHaveBeenCalled();
    });
});
