import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, setUnauthorizedHandler } from '../utils/api';
import { authApi } from '../utils/auth';
import { getCurrentUser, getReviewerName, hasRole, setCurrentUser } from '../utils/reviewer';
import LoginPage from '../pages/LoginPage';

const ADMIN = { email: 'admin@crx.test', display_name: 'Admin', role: 'admin' };

function renderLogin(onSignedIn = vi.fn()) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
        <QueryClientProvider client={queryClient}>
            <LoginPage onSignedIn={onSignedIn} />
        </QueryClientProvider>,
    );
    return onSignedIn;
}

describe('session identity', () => {
    beforeEach(() => {
        setCurrentUser(null);
        vi.restoreAllMocks();
    });

    afterEach(() => {
        setUnauthorizedHandler(null);
    });

    it('has no reviewer name until someone signs in', () => {
        expect(getReviewerName()).toBe('');
        expect(hasRole('reader')).toBe(false);
    });

    it('names the signed-in principal and answers role questions cumulatively', () => {
        setCurrentUser({ email: 'r@crx.test', display_name: 'Rae', role: 'reviewer' });
        expect(getReviewerName()).toBe('Rae');
        expect(hasRole('reader')).toBe(true);
        expect(hasRole('reviewer')).toBe(true);
        expect(hasRole('admin')).toBe(false);
    });

    it('falls back to the email when there is no display name', () => {
        setCurrentUser({ email: 'r@crx.test', display_name: '', role: 'reader' });
        expect(getReviewerName()).toBe('r@crx.test');
    });

    it('login stores the principal and logout clears it even if the call fails', async () => {
        vi.spyOn(api, 'post').mockResolvedValue(ADMIN);
        expect(await authApi.login('admin@crx.test', 'pw')).toEqual(ADMIN);
        expect(api.post).toHaveBeenCalledWith(
            '/auth/login',
            { email: 'admin@crx.test', password: 'pw' },
            false,
            { retry: true },
        );
        expect(getCurrentUser()).toEqual(ADMIN);

        vi.spyOn(api, 'post').mockRejectedValue(new Error('network gone'));
        await expect(authApi.logout()).rejects.toThrow('network gone');
        expect(getCurrentUser()).toBeNull();
    });

    it('me() reads a 401 as signed out, not as an error to show', async () => {
        const unauthorized = Object.assign(new Error('nope'), { status: 401 });
        vi.spyOn(api, 'get').mockRejectedValue(unauthorized);
        expect(await authApi.me()).toBeNull();

        vi.spyOn(api, 'get').mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
        await expect(authApi.me()).rejects.toThrow('boom');
    });
});

describe('login form', () => {
    beforeEach(() => {
        setCurrentUser(null);
        vi.restoreAllMocks();
    });

    it('signs in and hands the principal up', async () => {
        const post = vi.spyOn(api, 'post').mockResolvedValue(ADMIN);
        const onSignedIn = renderLogin();

        fireEvent.change(screen.getByLabelText('Email'), { target: { value: ' admin@crx.test ' } });
        fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a-long-password' } });
        fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));

        await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith(ADMIN));
        expect(post).toHaveBeenCalledWith(
            '/auth/login',
            {
                email: 'admin@crx.test',
                password: 'a-long-password',
            },
            false,
            { retry: true },
        );
    });

    it('shows why a sign-in failed and clears the password field', async () => {
        vi.spyOn(api, 'post').mockRejectedValue(new Error('email or password is incorrect'));
        const onSignedIn = renderLogin();

        fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'admin@crx.test' } });
        fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });
        fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));

        expect(await screen.findByRole('alert')).toHaveTextContent('email or password is incorrect');
        expect(onSignedIn).not.toHaveBeenCalled();
        expect(screen.getByLabelText('Password')).toHaveValue('');
    });

    it('explains a timed-out sign-in as the server not answering', async () => {
        const timeout = Object.assign(new Error('Request timed out'), { code: 'timeout' });
        vi.spyOn(api, 'post').mockRejectedValue(timeout);
        const onSignedIn = renderLogin();

        fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'admin@crx.test' } });
        fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret' } });
        fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));

        expect(await screen.findByRole('alert')).toHaveTextContent(
            'The server did not answer. Try again in a moment.',
        );
        expect(onSignedIn).not.toHaveBeenCalled();
        expect(screen.getByLabelText('Password')).toHaveValue('');
    });
});

describe('an expired session', () => {
    beforeEach(() => {
        setCurrentUser(ADMIN);
        vi.restoreAllMocks();
    });

    afterEach(() => {
        setUnauthorizedHandler(null);
    });

    it('a 401 from any call signs the app out once', async () => {
        const signedOut = vi.fn();
        setUnauthorizedHandler(signedOut);
        vi.stubGlobal(
            'fetch',
            vi.fn(async () => new Response(JSON.stringify({ code: 'unauthenticated' }), {
                status: 401,
                headers: { 'Content-Type': 'application/json' },
            })),
        );

        await expect(api.patch('/documents/d/sections/s/status', { review_status: 'approved' }))
            .rejects.toMatchObject({ status: 401, code: 'unauthenticated' });

        expect(signedOut).toHaveBeenCalledTimes(1);
        expect(getCurrentUser()).toBeNull();
    });

    it('a 403 is a permission problem, not a sign-out', async () => {
        const signedOut = vi.fn();
        setUnauthorizedHandler(signedOut);
        vi.stubGlobal(
            'fetch',
            vi.fn(async () => new Response(
                JSON.stringify({ code: 'forbidden', detail: 'this action needs the admin role' }),
                { status: 403, headers: { 'Content-Type': 'application/json' } },
            )),
        );

        await expect(api.post('/corpus/sync', {})).rejects.toMatchObject({
            status: 403,
            code: 'forbidden',
        });
        expect(signedOut).not.toHaveBeenCalled();
        expect(getCurrentUser()).toEqual(ADMIN);
    });

    it('sends the session cookie with every request', async () => {
        const fetchMock = vi.fn(async () => new Response('[]', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        }));
        vi.stubGlobal('fetch', fetchMock);

        await api.get('/documents');

        expect(fetchMock.mock.calls[0][1].credentials).toBe('include');
        expect(fetchMock.mock.calls[0][1].headers?.['X-Reviewer']).toBeUndefined();
    });
});
