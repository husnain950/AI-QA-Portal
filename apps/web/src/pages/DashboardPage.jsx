import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileText, CheckCircle, Clock, Trash2, Download, Loader2, Search, RefreshCw, Database } from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import NewVersionButton from '../components/review/NewVersionButton';
import { useDocumentStore } from '../stores/documentStore';
import DocumentHealth from '../components/dashboard/DocumentHealth';
import { api, corpusApi } from '../utils/api';
import { filterDocuments } from '../utils/documentFilters';
import { useUiStore } from '../stores/uiStore';

const DashboardPage = () => {
    const navigate = useNavigate();
    const { documents, fetchDocuments, deleteDocument, loading } = useDocumentStore();
    const pushToast = useUiStore((s) => s.pushToast);
    const confirmDialog = useUiStore((s) => s.confirmDialog);

    const [successMessage, setSuccessMessage] = useState('');
    const [documentQuery, setDocumentQuery] = useState('');
    const [sourceFilter, setSourceFilter] = useState('all');
    const [corpusStatus, setCorpusStatus] = useState(null);
    const [syncing, setSyncing] = useState(false);

    const refreshCorpusStatus = useCallback(async () => {
        try {
            const status = await corpusApi.status();
            setCorpusStatus(status);
        } catch {
            setCorpusStatus(null);
        }
    }, []);

    useEffect(() => {
        fetchDocuments();
        refreshCorpusStatus();
    }, [fetchDocuments, refreshCorpusStatus]);

    const handleCorpusSync = async () => {
        try {
            setSyncing(true);
            const summary = await corpusApi.sync({ metrics: true });
            const ord = summary.ordinance || {};
            const acts = summary.acts || {};
            setSuccessMessage(
                `Corpus sync finished — Ordinance imported ${ord.imported ?? 0} / skipped ${ord.skipped ?? 0}; `
                + `Acts imported ${acts.imported ?? 0} / skipped ${acts.skipped ?? 0}.`
            );
            setTimeout(() => setSuccessMessage(''), 8000);
            await fetchDocuments();
            await refreshCorpusStatus();
        } catch (err) {
            pushToast({ type: 'error', message: 'Corpus sync failed: ' + (err.message || 'Unknown error') });
        } finally {
            setSyncing(false);
        }
    };

    const handleDelete = async (docId, name, e) => {
        e.stopPropagation();
        const ok = await confirmDialog({
            title: 'Delete document?',
            message: `Delete "${name}"? This removes annotations, footnotes validation, and source files.`,
            confirmLabel: 'Delete',
        });
        if (!ok) return;
        try {
            await deleteDocument(docId);
        } catch (err) {
            pushToast({ type: 'error', message: 'Failed to delete document: ' + err.message });
        }
    };

    // Calculate aggregated metrics
    const totalDocs = documents.length;
    const totalSections = documents.reduce((sum, doc) => sum + doc.total_sections, 0);
    const totalIssues = documents.reduce((sum, doc) => sum + (doc.stats?.has_issues || 0), 0);
    const totalReviewed = documents.reduce((sum, doc) => sum + (doc.stats?.reviewed || 0), 0);
    const overallCompletion = totalSections > 0 ? Math.round((totalReviewed / totalSections) * 100) : 0;
    const filteredDocuments = filterDocuments(
        documents,
        documentQuery,
        sourceFilter,
    );

    const handleExport = (docId, format, e) => {
        e.stopPropagation();
        window.open(api.getDownloadUrl(`/documents/${docId}/export?format=${format}`));
    };

    const handleReviewClick = (docId) => {
        navigate(`/review/${docId}`);
    };

    return (
        <AppShell 
            title="Library"
            scrollable={true}
            actions={
                <div className="flex gap-2 align-center">
                    <button
                        className="btn btn-secondary"
                        onClick={handleCorpusSync}
                        disabled={syncing || corpusStatus?.sync_running}
                        title="Sync Ordinance + Acts from configured corpus mounts"
                    >
                        {syncing || corpusStatus?.sync_running ? (
                            <Loader2 size={16} className="animate-spin" />
                        ) : (
                            <RefreshCw size={16} />
                        )}
                        <span>{syncing ? 'Syncing…' : 'Sync corpus'}</span>
                    </button>
                    <button className="btn btn-primary" onClick={() => navigate('/upload')}>
                        <UploadCloud size={16} />
                        <span>Upload Document</span>
                    </button>
                </div>
            }
        >
            <div className="dashboard-container">
                {successMessage && (
                    <div className="flex align-center gap-2 p-3" style={{ 
                        backgroundColor: 'var(--color-success-light)', 
                        color: 'var(--color-success)', 
                        borderRadius: 'var(--radius-sm)', 
                        marginBottom: 24, 
                        fontSize: '0.85rem',
                        border: '1px solid var(--color-success)',
                        display: 'flex',
                        alignItems: 'center'
                    }}>
                        <CheckCircle size={16} />
                        <span>{successMessage}</span>
                    </div>
                )}

                {corpusStatus && (
                    <section
                        className="glass-panel"
                        style={{
                            padding: '14px 18px',
                            marginBottom: 20,
                            display: 'flex',
                            flexWrap: 'wrap',
                            gap: 16,
                            alignItems: 'center',
                            justifyContent: 'space-between',
                        }}
                    >
                        <div className="flex align-center gap-2" style={{ gap: 10 }}>
                            <Database size={16} style={{ color: 'var(--color-accent)' }} />
                            <div>
                                <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                                    Pipeline health
                                    {corpusStatus.last_status ? (
                                        <span style={{
                                            marginLeft: 8,
                                            color: corpusStatus.last_status === 'ok'
                                                ? 'var(--color-success)'
                                                : 'var(--color-warning)',
                                        }}>
                                            · last sync {corpusStatus.last_status}
                                        </span>
                                    ) : (
                                        <span style={{ marginLeft: 8, color: 'var(--color-text-muted)' }}>
                                            · never synced
                                        </span>
                                    )}
                                </div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                                    {corpusStatus.last_sync_at
                                        ? `Last sync ${new Date(corpusStatus.last_sync_at).toLocaleString()}`
                                        : 'Run Sync corpus (or make sync) to load Ordinance + Acts JSON'}
                                    {' · '}
                                    Ordinance {corpusStatus.ordinance_configured ? 'mounted' : 'missing'}
                                    {' / '}
                                    Acts {corpusStatus.acts_configured ? 'mounted' : 'missing'}
                                </div>
                            </div>
                        </div>
                    </section>
                )}

                {/* Stats Summary Grid */}
                <section className="stats-grid">
                    <div className="stat-card">
                        <div className="stat-value">{totalDocs}</div>
                        <div className="stat-label">Uploaded Documents</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value">{totalSections.toLocaleString()}</div>
                        <div className="stat-label">Total Sections</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value" style={{ color: totalIssues > 0 ? 'var(--color-warning)' : 'inherit' }}>
                            {totalIssues}
                        </div>
                        <div className="stat-label">Flagged sections</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value" style={{ color: 'var(--color-success)' }}>
                            {overallCompletion}%
                        </div>
                        <div className="stat-label">Overall Completion</div>
                    </div>
                </section>

                <section className="library-head">
                    <div>
                        <span className="library-kicker">Legal review library</span>
                        <h2>Acts and editions</h2>
                        <p>
                            Showing {filteredDocuments.length.toLocaleString()} of {documents.length.toLocaleString()} documents
                        </p>
                    </div>
                    <div className="library-controls">
                        <label className="document-search" htmlFor="document-filter">
                            <Search size={16} aria-hidden="true" />
                            <span className="sr-only">Filter documents</span>
                            <input
                                id="document-filter"
                                type="search"
                                value={documentQuery}
                                onChange={(event) => setDocumentQuery(event.target.value)}
                                placeholder="Find an Act or edition…"
                                autoComplete="off"
                            />
                        </label>
                        <div className="source-filters" role="group" aria-label="Document source">
                            {[
                                ['all', 'All'],
                                ['acts_corpus', 'ACT Corpus'],
                                ['upload', 'Manual Uploads'],
                            ].map(([value, label]) => (
                                <button
                                    key={value}
                                    type="button"
                                    className={`source-filter ${sourceFilter === value ? 'active' : ''}`}
                                    onClick={() => setSourceFilter(value)}
                                    aria-pressed={sourceFilter === value}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    </div>
                </section>

                {loading.documents ? (
                    <div style={{ textAlign: 'center', padding: 48, color: 'var(--color-text-muted)' }}>
                        Loading documents...
                    </div>
                ) : documents.length === 0 ? (
                    <div className="glass-panel" style={{ padding: '60px 20px', textAlign: 'center', border: '1px dashed var(--color-border)' }}>
                        <FileText size={48} style={{ color: 'var(--color-text-muted)', marginBottom: 16 }} />
                        <h3 style={{ marginBottom: 8 }}>Corpus is empty</h3>
                        <p style={{ color: 'var(--color-text-secondary)', marginBottom: 12, fontSize: '0.9rem', maxWidth: 520, marginLeft: 'auto', marginRight: 'auto' }}>
                            Seed from the configured Ordinance + Acts pipeline output, then review side-by-side.
                            Closed loop: convert → sync → review → export QA → import findings.
                        </p>
                        <p style={{ color: 'var(--color-text-muted)', marginBottom: 24, fontSize: '0.8rem' }}>
                            Prefer <code>make sync</code> on the host, or use Sync corpus when mounts are available.
                        </p>
                        <div className="flex gap-2" style={{ justifyContent: 'center' }}>
                            <button
                                className="btn btn-primary"
                                onClick={handleCorpusSync}
                                disabled={syncing || (!corpusStatus?.ordinance_configured && !corpusStatus?.acts_configured)}
                            >
                                {syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                                <span>Sync corpus now</span>
                            </button>
                            <button className="btn btn-secondary" onClick={() => navigate('/upload')}>
                                <UploadCloud size={16} />
                                <span>Upload PDF + JSON</span>
                            </button>
                        </div>
                    </div>
                ) : filteredDocuments.length === 0 ? (
                    <div className="glass-panel library-empty">
                        <Search size={32} aria-hidden="true" />
                        <h3>No matching documents</h3>
                        <p>Try another title or choose a different source filter.</p>
                    </div>
                ) : (
                    <div className="document-grid">
                        {filteredDocuments.map((doc) => {
                            const reviewedCount = doc.stats?.reviewed || 0;
                            const totalCount = doc.total_sections;
                            const compPercent = totalCount > 0 ? Math.round((reviewedCount / totalCount) * 100) : 0;
                            const isPending = compPercent === 0;

                            // SVG Progress Circle math
                            const strokeDashoffset = 251.2 - (251.2 * compPercent) / 100;

                            return (
                                <div 
                                    key={doc.id} 
                                    className="document-card"
                                    onClick={() => handleReviewClick(doc.id)}
                                >
                                    <div className="document-info">
                                        <div>
                                            <div className="document-title-row">
                                                <span className={`source-badge ${doc.source_type === 'acts_corpus' ? 'act' : 'upload'}`}>
                                                    {doc.source_type === 'acts_corpus' ? 'ACT Corpus' : 'Manual'}
                                                </span>
                                                <h3 className="document-name">{doc.name}</h3>
                                            </div>
                                            <div className="document-meta flex align-center gap-2">
                                                <Clock size={12} />
                                                <span>Uploaded on {new Date(doc.uploaded_at).toLocaleDateString()}</span>
                                            </div>
                                            
                                            <div className="document-stats-summary">
                                                <span className="document-stat-item">
                                                    <strong>{doc.total_sections}</strong> sections
                                                </span>
                                                <span className="document-stat-item">
                                                    <strong>{doc.total_pages}</strong> pages
                                                </span>
                                                <span
                                                    className="document-stat-item"
                                                    title="JSON versions of this parse (the PDF is fixed)"
                                                >
                                                    <strong>{doc.version_count ?? 1}</strong>{' '}
                                                    {doc.version_count === 1 ? 'version' : 'versions'}
                                                </span>
                                            </div>

                                            <DocumentHealth health={doc.health} />
                                        </div>

                                        {/* Actions */}
                                        <div className="flex gap-2" style={{ marginTop: 12 }}>
                                            <button 
                                                className="btn btn-primary"
                                                style={{ padding: '8px 14px', fontSize: '0.85rem' }}
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleReviewClick(doc.id);
                                                }}
                                            >
                                                {isPending ? 'Start Review' : 'Continue Review'}
                                            </button>
                                            
                                            <button 
                                                className="btn btn-secondary"
                                                style={{ padding: '8px 12px', fontSize: '0.85rem' }}
                                                onClick={(e) => handleExport(doc.id, 'json', e)}
                                                title="Export report as JSON"
                                            >
                                                <Download size={14} />
                                                <span>JSON</span>
                                            </button>

                                            <button 
                                                className="btn btn-secondary"
                                                style={{ padding: '8px 12px', fontSize: '0.85rem' }}
                                                onClick={(e) => handleExport(doc.id, 'csv', e)}
                                                title="Export report as CSV"
                                            >
                                                <Download size={14} />
                                                <span>CSV</span>
                                            </button>

                                            <span
                                                onClick={(e) => e.stopPropagation()}
                                                style={{ marginLeft: 'auto', display: 'inline-flex' }}
                                            >
                                                <NewVersionButton
                                                    documentId={doc.id}
                                                    documentName={doc.name}
                                                    className="btn btn-secondary"
                                                    style={{ padding: '8px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 6 }}
                                                    onSuccess={async () => {
                                                        setSuccessMessage('New JSON version is active. Open the document to see what changed.');
                                                        setTimeout(() => setSuccessMessage(''), 6000);
                                                        fetchDocuments();
                                                    }}
                                                />
                                            </span>
                                            
                                            <button 
                                                className="btn btn-danger"
                                                style={{ padding: '8px 12px' }}
                                                onClick={(e) => handleDelete(doc.id, doc.name, e)}
                                                title="Delete Document"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </div>

                                    {/* SVG Progress Circle */}
                                    <div className="progress-ring-container">
                                        <svg className="progress-ring-svg" width="90" height="90">
                                            <circle 
                                                className="progress-ring-bg" 
                                                cx="45" 
                                                cy="45" 
                                                r="36" 
                                            />
                                            <circle 
                                                className="progress-ring-bar" 
                                                cx="45" 
                                                cy="45" 
                                                r="36" 
                                                style={{
                                                    strokeDashoffset,
                                                    stroke: compPercent === 100 ? 'var(--color-success)' : 'var(--color-accent)'
                                                }}
                                            />
                                        </svg>
                                        <div className="progress-ring-text">
                                            {compPercent}%
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </AppShell>
    );
};

export default DashboardPage;
