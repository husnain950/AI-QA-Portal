import { getReviewerName, setReviewerName } from './reviewer';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
// Empty/unset in a prod build means same-origin — nginx proxies /uploads/ to the API.
// The localhost fallback is dev-only; baking it into a prod bundle sends every
// viewer's PDF request to their own machine.
const STATIC_BASE = import.meta.env.VITE_STATIC_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '');

export { getReviewerName, setReviewerName };

function withReviewer(headers = {}) {
    const reviewer = getReviewerName();
    return reviewer ? { ...headers, 'X-Reviewer': reviewer } : headers;
}

// The API runs one uvicorn worker on a small compute plan, so a cold or busy container
// makes the proxy return 502/503/504 before it answers. Retrying an idempotent GET once
// is the difference between a working Library and a page that claims the corpus is empty.
const TRANSIENT = new Set([502, 503, 504]);

export class ApiError extends Error {
    constructor(message, { status = 0, code = 'request_failed', details = null } = {}) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
        this.details = details;
        this.retryable = status === 0 || TRANSIENT.has(status);
    }
}

async function request(path, options = {}) {
    const { timeoutMs = 15_000, signal: callerSignal, ...fetchOptions } = options;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), timeoutMs);
    const abort = () => controller.abort(callerSignal?.reason);
    callerSignal?.addEventListener('abort', abort, { once: true });
    try {
        const res = await fetch(`${API_BASE}${path}`, {
            ...fetchOptions,
            headers: withReviewer(fetchOptions.headers),
            signal: controller.signal,
        });
        if (!res.ok) {
            const payload = await res.json().catch(() => ({}));
            const detail = payload.detail;
            const message = typeof detail === 'string'
                ? detail
                : detail?.message || payload.message || `API returned ${res.status}`;
            throw new ApiError(message, {
                status: res.status,
                code: payload.code || detail?.code || 'request_failed',
                details: payload,
            });
        }
        return res;
    } catch (error) {
        if (error instanceof ApiError) throw error;
        if (controller.signal.aborted) {
            throw new ApiError(
                callerSignal?.aborted ? 'Request cancelled' : 'Request timed out',
                { code: callerSignal?.aborted ? 'cancelled' : 'timeout' },
            );
        }
        throw new ApiError(error?.message || 'Network error', { code: 'network_error' });
    } finally {
        clearTimeout(timeout);
        callerSignal?.removeEventListener('abort', abort);
    }
}

export const api = {
    async get(path, options = {}) {
        let res;
        try {
            res = await request(path, { ...options, method: 'GET' });
        } catch (error) {
            if (!error.retryable || options.signal?.aborted) throw error;
        }
        if (!res) {
            await new Promise((resolve) => setTimeout(resolve, 750));
            res = await request(path, { ...options, method: 'GET' });
        }
        if (TRANSIENT.has(res.status)) {
            await new Promise((resolve) => setTimeout(resolve, 750));
            res = await request(path, { ...options, method: 'GET' });
        }
        return res.json();
    },

    async post(path, body, isMultipart = false, options = {}) {
        const res = await request(path, {
            method: 'POST',
            ...options,
            headers: {
                ...(isMultipart ? {} : { 'Content-Type': 'application/json' }),
                ...(options.headers || {}),
            },
            body: isMultipart ? body : JSON.stringify(body),
        });
        return res.json();
    },

    async patch(path, body) {
        const res = await request(path, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return res.json();
    },

    async delete(path) {
        const res = await request(path, {
            method: 'DELETE',
        });
        return res.status === 204 ? null : res.json();
    },
    
    getDownloadUrl(path) {
        return `${API_BASE}${path}`;
    },

    getAssetUrl(path) {
        if (!path) return '';
        if (/^https?:\/\//i.test(path)) return path;
        return `${STATIC_BASE}${path.startsWith('/') ? path : `/${path}`}`;
    },

    getFileUrl(filename) {
        const encoded = String(filename || '')
            .split('/')
            .map(encodeURIComponent)
            .join('/');
        return `${STATIC_BASE}/uploads/${encoded}`;
    }
};

export const jobsApi = {
    start(type, payload = {}, { idempotencyKey } = {}) {
        return api.post(`/v2/jobs/${encodeURIComponent(type)}`, payload, false, {
            headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
        });
    },

    get(jobId, options = {}) {
        return api.get(`/v2/jobs/${encodeURIComponent(jobId)}`, options);
    },

    cancel(jobId) {
        return api.post(`/v2/jobs/${encodeURIComponent(jobId)}/cancel`, {});
    },

    async wait(jobId, { signal, onProgress, pollMs = 750, timeoutMs = 30 * 60_000 } = {}) {
        const started = Date.now();
        while (true) {
            if (signal?.aborted) {
                throw new ApiError('Request cancelled', { code: 'cancelled' });
            }
            const job = await this.get(jobId, { signal });
            onProgress?.(job);
            if (job.state === 'succeeded') return job.result;
            if (job.state === 'failed') {
                throw new ApiError(job.error?.message || 'Background job failed', {
                    code: job.error?.type || 'job_failed',
                    details: job.error,
                });
            }
            if (job.state === 'cancelled') {
                throw new ApiError('Background job was cancelled', { code: 'cancelled' });
            }
            if (Date.now() - started > timeoutMs) {
                throw new ApiError('Background job timed out', { code: 'timeout' });
            }
            await new Promise((resolve) => setTimeout(resolve, pollMs));
        }
    },

    async run(type, payload = {}, options = {}) {
        const created = await this.start(type, payload, options);
        return this.wait(created.job_id, options);
    },
};


/** Corpus sync / health for the configured Ordinance + Acts roots. */
export const corpusApi = {
    status() {
        return api.get('/corpus/status');
    },
    async sync(body = { metrics: true }, options = {}) {
        const created = await api.post('/corpus/sync', body, false, {
            headers: options.idempotencyKey
                ? { 'Idempotency-Key': options.idempotencyKey }
                : {},
        });
        if (!created.job_id) return created;
        return jobsApi.wait(created.job_id, options);
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

    async create(documentId, file, { note } = {}) {
        const current = (await this.list(documentId)).find((version) => version.is_active);
        if (!current) throw new ApiError('Document has no active version', { code: 'active_version_missing' });
        const form = new FormData();
        form.append('json_file', file);
        if (note) form.append('note', note);
        return api.post(`/documents/${documentId}/versions`, form, true, {
            headers: { 'If-Match': current.id },
            timeoutMs: 60_000,
        });
    },

    async activate(documentId, versionId, expectedVersionId = null) {
        const current = expectedVersionId
            || (await this.list(documentId)).find((version) => version.is_active)?.id;
        if (!current) throw new ApiError('Document has no active version', { code: 'active_version_missing' });
        return api.post(
            `/documents/${documentId}/versions/${versionId}/activate`,
            {},
            false,
            { headers: { 'If-Match': current } },
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

    async request(documentId, sectionId, instructions, modelName, options = {}) {
        const result = await jobsApi.run('ai_proposal', {
            document_id: documentId,
            section_id: sectionId,
            instructions,
            model: modelName || null,
        }, options);
        return this.get(result.proposal_id);
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
