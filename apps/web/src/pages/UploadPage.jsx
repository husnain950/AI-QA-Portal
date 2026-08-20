import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, AlertCircle, CheckCircle2, ChevronRight, Loader2 } from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import { api } from '../utils/api';

const UploadPage = () => {
    const navigate = useNavigate();
    const [pdfFile, setPdfFile] = useState(null);
    const [jsonFile, setJsonFile] = useState(null);
    const [documentName, setDocumentName] = useState('');
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState('');
    const [preflight, setPreflight] = useState(null);
    
    // JSON Validation details
    const [jsonStats, setJsonStats] = useState(null);
    const [jsonValidating, setJsonValidating] = useState(false);

    const pdfInputRef = useRef(null);
    const jsonInputRef = useRef(null);

    const processPdfFile = (file) => {
        if (file && file.type === 'application/pdf') {
            setPdfFile(file);
            setPreflight(null);
            setError('');
            // Pre-fill doc name if empty
            if (!documentName) {
                const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
                setDocumentName(cleanName);
            }
        } else {
            setError('Please upload a valid PDF file.');
        }
    };

    const processJsonFile = (file) => {
        if (file && file.name.endsWith('.json')) {
            setJsonFile(file);
            setPreflight(null);
            setError('');
            validateJsonLocally(file);
        } else {
            setError('Please upload a valid JSON file.');
        }
    };

    const handlePdfChange = (e) => {
        const file = e.target.files[0];
        processPdfFile(file);
    };

    const handleJsonChange = (e) => {
        const file = e.target.files[0];
        processJsonFile(file);
    };

    // Drag-and-drop state & handlers
    const [isPdfDragActive, setIsPdfDragActive] = useState(false);
    const [isJsonDragActive, setIsJsonDragActive] = useState(false);

    const handlePdfDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setIsPdfDragActive(true);
        } else if (e.type === "dragleave") {
            setIsPdfDragActive(false);
        }
    };

    const handlePdfDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsPdfDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            processPdfFile(e.dataTransfer.files[0]);
        }
    };

    const handleJsonDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setIsJsonDragActive(true);
        } else if (e.type === "dragleave") {
            setIsJsonDragActive(false);
        }
    };

    const handleJsonDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsJsonDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            processJsonFile(e.dataTransfer.files[0]);
        }
    };

    // Client-side JSON validation
    const validateJsonLocally = (file) => {
        setJsonValidating(true);
        setJsonStats(null);
        
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const parsed = JSON.parse(e.target.result);
                
                // Inspect structures
                const chapters = parsed.chapters || [];
                const schedules = parsed.schedules || [];
                
                let sectionCount = 0;
                let sectionsWithHtml = 0;
                let footnoteCount = 0;

                const countSections = (secList) => {
                    secList.forEach(s => {
                        sectionCount++;
                        if (s.html) sectionsWithHtml++;
                        if (s.footnotes) footnoteCount += s.footnotes.length;
                    });
                };

                const traverse = (node) => {
                    if (node.sections) countSections(node.sections);
                    if (node.parts) node.parts.forEach(traverse);
                    if (node.divisions) node.divisions.forEach(traverse);
                };

                chapters.forEach(traverse);
                schedules.forEach(traverse);

                setJsonStats({
                    isValid: true,
                    chaptersCount: chapters.length,
                    schedulesCount: schedules.length,
                    sectionsCount: sectionCount,
                    sectionsWithHtml,
                    footnoteCount,
                    message: 'JSON Schema holds valid structure'
                });
            } catch (err) {
                setJsonStats({
                    isValid: false,
                    message: 'Invalid JSON format: ' + err.message
                });
            } finally {
                setJsonValidating(false);
            }
        };
        reader.readAsText(file);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!pdfFile || !jsonFile || !documentName.trim()) {
            setError('Please fill in all fields.');
            return;
        }

        if (jsonStats && !jsonStats.isValid) {
            setError('Please fix the JSON schema errors before uploading.');
            return;
        }

        setUploading(true);
        setError('');

        const formData = new FormData();
        formData.append('pdf', pdfFile);
        formData.append('json_file', jsonFile);

        try {
            const checked = await api.post('/v2/uploads/preflight', formData, true, {
                timeoutMs: 5 * 60_000,
            });
            setPreflight(checked);
            const res = await api.post('/v2/documents', {
                token: checked.token,
                name: documentName.trim(),
                corpus_lane: 'manual',
            }, false, { timeoutMs: 60_000 });
            navigate(`/review/${res.id}`);
        } catch (err) {
            const errors = err.details?.detail?.errors;
            setError(Array.isArray(errors)
                ? errors.map((item) => `${item.pointer}: ${item.message}`).join(' · ')
                : err.message || 'File upload failed. Ensure the server is running.');
        } finally {
            setUploading(false);
        }
    };

    return (
        <AppShell title="Upload" showBackButton={true} scrollable={true}>
            <div className="upload-container surface-panel">
                <h2 className="upload-title">Upload QA review pair</h2>
                <p className="upload-sub">
                    The PDF is the fixed source render; the JSON is the parsed structure to review against it.
                </p>

                {error && (
                    <div className="upload-error" role="alert">
                        <AlertCircle size={16} aria-hidden="true" />
                        <span>{error}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                    <div className="upload-dropzones">
                        {/* PDF Dropzone */}
                        <div>
                            <span className="form-label">PDF file (original render)</span>
                            <input
                                type="file"
                                ref={pdfInputRef}
                                className="sr-only"
                                accept="application/pdf"
                                onChange={handlePdfChange}
                            />
                            <button
                                type="button"
                                className={`dropzone ${isPdfDragActive ? 'active' : ''}`}
                                onClick={() => pdfInputRef.current.click()}
                                onDragEnter={handlePdfDrag}
                                onDragOver={handlePdfDrag}
                                onDragLeave={handlePdfDrag}
                                onDrop={handlePdfDrop}
                                aria-label="Choose or drop the PDF file"
                            >
                                <UploadCloud size={30} style={{ color: pdfFile ? 'var(--color-success)' : 'var(--color-text-muted)' }} />
                                {pdfFile ? (
                                    <div className="dropzone-file-selected">
                                        <CheckCircle2 size={16} />
                                        <span>{pdfFile.name} ({(pdfFile.size / (1024*1024)).toFixed(2)} MB)</span>
                                    </div>
                                ) : (
                                    <span className="dropzone-text">Click or drop the PDF file here</span>
                                )}
                            </button>
                        </div>

                        {/* JSON Dropzone */}
                        <div>
                            <span className="form-label">JSON file (parsed structure)</span>
                            <input
                                type="file"
                                ref={jsonInputRef}
                                className="sr-only"
                                accept=".json"
                                onChange={handleJsonChange}
                            />
                            <button
                                type="button"
                                className={`dropzone ${isJsonDragActive ? 'active' : ''}`}
                                onClick={() => jsonInputRef.current.click()}
                                onDragEnter={handleJsonDrag}
                                onDragOver={handleJsonDrag}
                                onDragLeave={handleJsonDrag}
                                onDrop={handleJsonDrop}
                                aria-label="Choose or drop the JSON file"
                            >
                                <UploadCloud size={30} style={{ color: jsonFile ? (jsonStats?.isValid ? 'var(--color-success)' : 'var(--color-error)') : 'var(--color-text-muted)' }} />
                                {jsonFile ? (
                                    <div className="dropzone-file-selected" style={{ color: jsonStats?.isValid ? 'var(--color-success)' : 'var(--color-error)' }}>
                                        {jsonStats?.isValid ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                        <span>{jsonFile.name} ({(jsonFile.size / (1024*1024)).toFixed(2)} MB)</span>
                                    </div>
                                ) : (
                                    <span className="dropzone-text">Click or drop the enriched JSON file here</span>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* Document Display Name */}
                    <div className="form-group">
                        <label className="form-label" htmlFor="upload-doc-name">Display name</label>
                        <input
                            id="upload-doc-name"
                            type="text"
                            className="form-input"
                            placeholder="e.g. Income Tax Ordinance, 2001 (Amended 2018)"
                            value={documentName}
                            onChange={(e) => setDocumentName(e.target.value)}
                            required
                        />
                    </div>

                    {/* JSON Validation Panel */}
                    {jsonValidating && (
                        <div className="upload-validating">Validating JSON schema…</div>
                    )}
                    {jsonStats && (
                        <div className={`upload-validation ${jsonStats.isValid ? 'is-valid' : 'is-invalid'}`}>
                            <h4>
                                {jsonStats.isValid ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                <span>{jsonStats.message}</span>
                            </h4>
                            {jsonStats.isValid && (
                                <ul>
                                    <li>Detected <strong>{jsonStats.chaptersCount}</strong> chapters, <strong>{jsonStats.schedulesCount}</strong> schedules</li>
                                    <li>Found <strong>{jsonStats.sectionsCount}</strong> sections (<strong>{jsonStats.sectionsWithHtml}</strong> containing HTML content)</li>
                                    <li>Found <strong>{jsonStats.footnoteCount}</strong> footnotes</li>
                                </ul>
                            )}
                        </div>
                    )}

                    {preflight && (
                        <div className="upload-validation is-valid" role="status">
                            <h4><CheckCircle2 size={16} /> Server preflight passed</h4>
                            <ul>
                                <li>{preflight.pages} PDF pages</li>
                                <li>{preflight.sections} reviewable sections</li>
                                <li>{preflight.footnotes} footnotes</li>
                                <li>Staging expires {new Date(preflight.expires_at).toLocaleString()}</li>
                            </ul>
                        </div>
                    )}

                    {/* Action buttons */}
                    <button
                        type="submit"
                        className="btn btn-primary upload-submit"
                        disabled={uploading || !pdfFile || !jsonFile || !documentName.trim() || (jsonStats && !jsonStats.isValid)}
                    >
                        {uploading ? (
                            <>
                                <Loader2 className="animate-spin" size={18} />
                                <span>Validating, staging, and committing…</span>
                            </>
                        ) : (
                            <>
                                <span>Upload and start review</span>
                                <ChevronRight size={18} />
                            </>
                        )}
                    </button>
                </form>
            </div>
        </AppShell>
    );
};

export default UploadPage;
