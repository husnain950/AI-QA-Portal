import React, { useState, useRef } from 'react';
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
    
    // JSON Validation details
    const [jsonStats, setJsonStats] = useState(null);
    const [jsonValidating, setJsonValidating] = useState(false);

    const pdfInputRef = useRef(null);
    const jsonInputRef = useRef(null);

    const processPdfFile = (file) => {
        if (file && file.type === 'application/pdf') {
            setPdfFile(file);
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
        formData.append('name', documentName.trim());

        try {
            const res = await api.post('/documents/upload', formData, true);
            navigate(`/review/${res.id}`);
        } catch (err) {
            console.error(err);
            setError(err.message || 'File upload failed. Ensure the server is running.');
        } finally {
            setUploading(false);
        }
    };

    return (
        <AppShell title="Upload Document Pair" showBackButton={true} scrollable={true}>
            <div className="upload-container glass-panel" style={{ padding: 40, marginTop: 40, border: '1px solid var(--color-border)' }}>
                <h2 style={{ marginBottom: 24, fontSize: '1.5rem', fontFamily: 'var(--font-heading)' }}>
                    Upload QA Review Pair
                </h2>

                {error && (
                    <div className="flex align-center gap-2 p-3" style={{ backgroundColor: 'var(--color-error-light)', color: 'var(--color-error)', borderRadius: 'var(--radius-sm)', marginBottom: 20, fontSize: '0.85rem' }}>
                        <AlertCircle size={16} />
                        <span>{error}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                    {/* PDF Dropzone */}
                    <div>
                        <span className="form-label">PDF File (Original Render)</span>
                        <div 
                            className={`dropzone ${isPdfDragActive ? 'active' : ''}`}
                            onClick={() => pdfInputRef.current.click()}
                            onDragEnter={handlePdfDrag}
                            onDragOver={handlePdfDrag}
                            onDragLeave={handlePdfDrag}
                            onDrop={handlePdfDrop}
                        >
                            <input 
                                type="file" 
                                ref={pdfInputRef} 
                                style={{ display: 'none' }} 
                                accept="application/pdf"
                                onChange={handlePdfChange}
                            />
                            <UploadCloud size={32} style={{ color: pdfFile ? 'var(--color-success)' : 'var(--color-text-muted)' }} />
                            {pdfFile ? (
                                <div className="dropzone-file-selected">
                                    <CheckCircle2 size={16} />
                                    <span>{pdfFile.name} ({(pdfFile.size / (1024*1024)).toFixed(2)} MB)</span>
                                </div>
                            ) : (
                                <span className="dropzone-text">Click or drop the PDF file here</span>
                            )}
                        </div>
                    </div>

                    {/* JSON Dropzone */}
                    <div>
                        <span className="form-label">JSON File (Parsed Structure)</span>
                        <div 
                            className={`dropzone ${isJsonDragActive ? 'active' : ''}`}
                            onClick={() => jsonInputRef.current.click()}
                            onDragEnter={handleJsonDrag}
                            onDragOver={handleJsonDrag}
                            onDragLeave={handleJsonDrag}
                            onDrop={handleJsonDrop}
                        >
                            <input 
                                type="file" 
                                ref={jsonInputRef} 
                                style={{ display: 'none' }} 
                                accept=".json"
                                onChange={handleJsonChange}
                            />
                            <UploadCloud size={32} style={{ color: jsonFile ? (jsonStats?.isValid ? 'var(--color-success)' : 'var(--color-error)') : 'var(--color-text-muted)' }} />
                            {jsonFile ? (
                                <div className="dropzone-file-selected" style={{ color: jsonStats?.isValid ? 'var(--color-success)' : 'var(--color-error)' }}>
                                    {jsonStats?.isValid ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                    <span>{jsonFile.name} ({(jsonFile.size / (1024*1024)).toFixed(2)} MB)</span>
                                </div>
                            ) : (
                                <span className="dropzone-text">Click or drop the enriched JSON file here</span>
                            )}
                        </div>
                    </div>

                    {/* Document Display Name */}
                    <div className="form-group">
                        <label className="form-label">Display Name</label>
                        <input
                            type="text"
                            className="form-input"
                            placeholder="e.g. Income Tax Ordinance, 2001 (Amended 2018)"
                            value={documentName}
                            onChange={(e) => setDocumentName(e.target.value)}
                            required
                        />
                    </div>

                    {/* JSON Validation Panel */}
                    {jsonValidating && <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Validating JSON schema...</div>}
                    {jsonStats && (
                        <div 
                            className="glass-panel" 
                            style={{ 
                                padding: 16, 
                                fontSize: '0.85rem', 
                                border: '1px solid',
                                borderColor: jsonStats.isValid ? 'var(--color-success)' : 'var(--color-error)',
                                backgroundColor: jsonStats.isValid ? 'var(--color-success-light)' : 'var(--color-error-light)'
                            }}
                        >
                            <h4 style={{ marginBottom: 8, display: 'flex', align: 'center', gap: 6, color: jsonStats.isValid ? 'var(--color-success)' : 'var(--color-error)' }}>
                                {jsonStats.isValid ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                <span>{jsonStats.message}</span>
                            </h4>
                            {jsonStats.isValid && (
                                <ul style={{ marginLeft: 16 }}>
                                    <li>Detected <strong>{jsonStats.chaptersCount}</strong> Chapters, <strong>{jsonStats.schedulesCount}</strong> Schedules</li>
                                    <li>Found <strong>{jsonStats.sectionsCount}</strong> sections (<strong>{jsonStats.sectionsWithHtml}</strong> containing HTML content)</li>
                                    <li>Found <strong>{jsonStats.footnoteCount}</strong> footnotes</li>
                                </ul>
                            )}
                        </div>
                    )}

                    {/* Action buttons */}
                    <button 
                        type="submit" 
                        className="btn btn-primary"
                        style={{ marginTop: 12, padding: '12px' }}
                        disabled={uploading || !pdfFile || !jsonFile || !documentName.trim() || (jsonStats && !jsonStats.isValid)}
                    >
                        {uploading ? (
                            <>
                                <Loader2 className="animate-spin" size={18} />
                                <span>Processing Files & Splitting Sections...</span>
                            </>
                        ) : (
                            <>
                                <span>Upload and Start Review</span>
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
