import { api } from './api';
import { setCurrentUser } from './reviewer';

export const authApi = {
    async login(email, password) {
        const user = await api.post('/auth/login', { email, password });
        return setCurrentUser(user);
    },

    async logout() {
        try {
            await api.post('/auth/logout', {});
        } finally {
            setCurrentUser(null);
        }
    },

    /** The signed-in principal, or null. A 401 here is the normal signed-out answer. */
    async me() {
        try {
            return setCurrentUser(await api.get('/auth/me', { retry: false }));
        } catch (error) {
            if (error.status === 401) return setCurrentUser(null);
            throw error;
        }
    },
};
