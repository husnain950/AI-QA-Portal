const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const REVIEWER_KEY = 'qa-portal-reviewer';

export function getReviewerName() {
    try {
        const stored = window.localStorage?.getItem(REVIEWER_KEY);
        if (stored && stored.trim()) return stored.trim();
    } catch (_) {}
    return 'anonymous';
}

export function setReviewerName(name) {
    const value = String(name || '').trim() || 'anonymous';
    try {
        window.localStorage?.setItem(REVIEWER_KEY, value);
    } catch (_) {}
    return value;
}

function withReviewer(headers = {}) {
    return { ...headers, 'X-Reviewer': getReviewerName() };
}

export const api = {
    async get(path) {
        const res = await fetch(`${API_BASE}${path}`, { headers: withReviewer() });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Network error' }));
            throw new Error(err.detail || 'API request failed');
        }
        return res.json();
    },

    async post(path, body, isMultipart = false) {
        const headers = withReviewer(isMultipart ? {} : { 'Content-Type': 'application/json' });
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'POST',
            headers,
            body: isMultipart ? body : JSON.stringify(body)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Network error' }));
            throw new Error(err.detail || 'API request failed');
        }
        return res.json();
    },

    async patch(path, body) {
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'PATCH',
            headers: withReviewer({ 'Content-Type': 'application/json' }),
            body: JSON.stringify(body)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Network error' }));
            throw new Error(err.detail || 'API request failed');
        }
        return res.json();
    },

    async delete(path) {
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'DELETE',
            headers: withReviewer(),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Network error' }));
            throw new Error(err.detail || 'API request failed');
        }
        return res.status === 204 ? null : res.json();
    },
    
    getDownloadUrl(path) {
        return `${API_BASE}${path}`;
    },

    getFileUrl(filename) {
        const encoded = String(filename || '')
            .split('/')
            .map(encodeURIComponent)
            .join('/');
        return `${import.meta.env.VITE_STATIC_URL || 'http://localhost:8000'}/uploads/${encoded}`;
    }
};


/** Corpus sync / health for the configured Ordinance + Acts roots. */
export const corpusApi = {
    status() {
        return api.get('/corpus/status');
    },
    sync(body = { metrics: true }) {
        return api.post('/corpus/sync', body);
    },
};

/** JSON versions of a document. The PDF is static; only the parse is versioned. */
export const versionsApi = {
    list(documentId) {
        return api.get(`/documents/${documentId}/versions`);
    },

    create(documentId, file, { note, reviewerName } = {}) {
        const form = new FormData();
        form.append('json_file', file);
        if (note) form.append('note', note);
        if (reviewerName) form.append('reviewer_name', reviewerName);
        return api.post(`/documents/${documentId}/versions`, form, true);
    },

    activate(documentId, versionId) {
        return api.post(
            `/documents/${documentId}/versions/${versionId}/activate`,
            {},
        );
    },

    diff(documentId, versionId, againstId) {
        const query = againstId ? `?against=${encodeURIComponent(againstId)}` : '';
        return api.get(`/documents/${documentId}/versions/${versionId}/diff${query}`);
    },
};
