import { getReviewerName, setReviewerName } from './reviewer';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
// Empty/unset in a prod build means same-origin — nginx proxies /uploads/ to the API.
// The localhost fallback is dev-only; baking it into a prod bundle sends every
// viewer's PDF request to their own machine.
const STATIC_BASE = import.meta.env.VITE_STATIC_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '');

export { getReviewerName, setReviewerName };

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
        return `${STATIC_BASE}/uploads/${encoded}`;
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

    editions(documentId) {
        return api.get(`/documents/${documentId}/editions`);
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

/**
 * AI fix loop: ask the model for a corrected leaf, then a human approves or
 * rejects it. Approval creates a new JSON version plus a persistent overlay
 * that survives corpus re-syncs.
 */
export const aiFixApi = {
    models() {
        return api.get('/ai-fixes/models');
    },

    request(documentId, sectionId, instructions, modelName) {
        return api.post(
            `/documents/${documentId}/sections/${sectionId}/ai-fix`,
            { instructions, model_name: modelName || null },
        );
    },

    list(documentId, sectionId) {
        const query = sectionId ? `?section_id=${encodeURIComponent(sectionId)}` : '';
        return api.get(`/documents/${documentId}/ai-fixes${query}`);
    },

    get(proposalId) {
        return api.get(`/ai-fixes/${proposalId}`);
    },

    approve(proposalId) {
        return api.post(`/ai-fixes/${proposalId}/approve`, {});
    },

    reject(proposalId) {
        return api.post(`/ai-fixes/${proposalId}/reject`, {});
    },
};
