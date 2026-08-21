import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * A prod bundle built with VITE_STATIC_URL unset used to bake
 * http://localhost:8000 into every PDF URL, so anyone but the developer got
 * "Failed to load PDF / Failed to fetch". Pin both branches.
 */
describe('api.getFileUrl', () => {
    afterEach(() => {
        vi.unstubAllEnvs();
        vi.resetModules();
    });

    async function loadApi() {
        vi.resetModules();
        return (await import('../utils/api')).api;
    }

    it('stays same-origin in a prod build with no VITE_STATIC_URL', async () => {
        vi.stubEnv('VITE_STATIC_URL', '');
        vi.stubEnv('DEV', false);
        const api = await loadApi();
        expect(api.getFileUrl('pdf/abc.pdf')).toBe('/uploads/pdf/abc.pdf');
    });

    it('stays same-origin in dev so the Vite proxy can forward /uploads', async () => {
        vi.stubEnv('VITE_STATIC_URL', '');
        vi.stubEnv('DEV', true);
        const api = await loadApi();
        expect(api.getFileUrl('pdf/abc.pdf')).toBe('/uploads/pdf/abc.pdf');
    });

    it('honours an explicit static origin', async () => {
        vi.stubEnv('VITE_STATIC_URL', 'https://files.example.com');
        vi.stubEnv('DEV', false);
        const api = await loadApi();
        expect(api.getFileUrl('pdf/a b.pdf')).toBe('https://files.example.com/uploads/pdf/a%20b.pdf');
    });
});
