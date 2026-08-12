import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, AlertTriangle, ArrowLeft, ArrowRight, Loader2, Clock, Sparkles } from 'lucide-react';
import { useDocumentStore } from '../../stores/documentStore';
import {
    formatQualityFlagList,
    hasAnyQualityFlags,
} from '../../utils/qualityFlags';
import { useUiStore } from '../../stores/uiStore';
import { useAiFixStore } from '../../stores/aiFixStore';
import { hasApprovedFix } from '../../utils/aiFix';
import AiFixPanel from './AiFixPanel';

/**
 * @param {{ section?: object | null }} props
 * Optional `section` defaults to activeSection so page-view can render
 * one toolbar per card.
 */
const ReviewToolbar = ({ section: sectionProp = null } = {}) => {
    const navigate = useNavigate();
    const pushToast = useUiStore((s) => s.pushToast);
    const confirmDialog = useUiStore((s) => s.confirmDialog);
    const {
        activeDocument,
        sections,
        activeSection,
        updateSectionStatus,
        fetchDocument,
        fetchSections,
        fetchSection,
        loading,
    } = useDocumentStore();
    const [aiFixOpen, setAiFixOpen] = useState(false);
    const aiProposals = useAiFixStore((s) => s.proposals);

    const targetSection = sectionProp || activeSection;
    if (!targetSection || !activeDocument) return null;

    const aiFixed = hasApprovedFix(aiProposals, targetSection.id);

    const currentIndex = sections.findIndex((s) => s.id === targetSection.id);
    const hasPrev = currentIndex > 0;
    const hasNext = currentIndex >= 0 && currentIndex < sections.length - 1;
    const qualityReasons = formatQualityFlagList(targetSection.quality_flags);
    // Approve gate: any flag (incl. page_range_out_of_bounds) needs confirm.
    const needsQualityOverride = hasAnyQualityFlags(targetSection.quality_flags);
    const status = targetSection.review_status;

    const navigateToSection = (index) => {
        if (index < 0 || index >= sections.length) return;
        const targetSec = sections[index];
        navigate(`/review/${activeDocument.id}/${targetSec.id}`);
    };

    const handleApprove = async () => {
        if (needsQualityOverride) {
            const listed = qualityReasons.map((r) => `• ${r}`).join('\n');
            const confirmed = await confirmDialog({
                title: 'Override parse-quality flags?',
                message: `${listed}\n\nApprove this section anyway?`,
                confirmLabel: 'Approve anyway',
            });
            if (!confirmed) return;
        }
        try {
            await updateSectionStatus(activeDocument.id, targetSection.id, 'approved');
            if (hasNext) {
                setTimeout(() => navigateToSection(currentIndex + 1), 300);
            }
        } catch (e) {
            pushToast({ type: 'error', message: `Failed to update status: ${e.message}` });
        }
    };

    const handleFlag = async () => {
        try {
            await updateSectionStatus(activeDocument.id, targetSection.id, 'has_issues');
        } catch (e) {
            pushToast({ type: 'error', message: `Failed to update status: ${e.message}` });
        }
    };

    const handlePending = async () => {
        try {
            await updateSectionStatus(activeDocument.id, targetSection.id, 'pending');
        } catch (e) {
            pushToast({ type: 'error', message: `Failed to update status: ${e.message}` });
        }
    };

    return (
        <div className="review-toolbar glass-panel" style={{ gap: 12, overflow: 'hidden', padding: '0 16px' }}>
            <div className="flex align-center gap-2" style={{ flexShrink: 0 }}>
                {loading.activeSection ? (
                    <Loader2 className="animate-spin" size={14} style={{ color: 'var(--color-accent)' }} />
                ) : (
                    <>
                        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                            Status:
                        </span>
                        <span
                            className={`badge badge-${status === 'has_issues' ? 'flagged' : status === 'approved_inherited' ? 'approved' : status}`}
                            style={{ fontSize: '0.75rem', padding: '3px 8px', whiteSpace: 'nowrap' }}
                        >
                            {status === 'has_issues' ? 'flagged' : status === 'approved_inherited' ? 'inherited' : status}
                        </span>
                        {aiFixed && (
                            <span
                                className="badge ai-fix-badge"
                                title="An approved AI fix is applied to this section"
                                style={{ fontSize: '0.7rem', padding: '3px 8px', whiteSpace: 'nowrap' }}
                            >
                                <Sparkles size={11} /> AI fixed
                            </span>
                        )}
                    </>
                )}
            </div>

            <div className="flex align-center gap-2" style={{ justifyContent: 'center', flex: 1 }}>
                <button
                    className={`btn ${status === 'pending' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                        padding: '6px 12px',
                        fontSize: '0.8rem',
                        backgroundColor: status === 'pending' ? 'var(--color-border)' : 'transparent',
                        borderColor: 'var(--color-border)',
                        color: status === 'pending' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                        whiteSpace: 'nowrap',
                    }}
                    onClick={handlePending}
                    disabled={loading.activeSection}
                    title="Mark Section as Pending"
                >
                    <Clock size={14} />
                    <span>Pending</span>
                </button>

                <button
                    className={`btn ${status === 'approved' || status === 'approved_inherited' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                        padding: '6px 12px',
                        fontSize: '0.8rem',
                        backgroundColor: status === 'approved' || status === 'approved_inherited' ? 'var(--color-success)' : 'transparent',
                        borderColor: status === 'approved' || status === 'approved_inherited' ? 'var(--color-success)' : 'var(--color-border)',
                        color: status === 'approved' || status === 'approved_inherited' ? '#ffffff' : 'var(--color-text-secondary)',
                        whiteSpace: 'nowrap',
                    }}
                    onClick={handleApprove}
                    disabled={loading.activeSection}
                    title="Approve Section & Move Next"
                >
                    <Check size={14} />
                    <span>Approve</span>
                </button>

                <button
                    className={`btn ${status === 'has_issues' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                        padding: '6px 12px',
                        fontSize: '0.8rem',
                        backgroundColor: status === 'has_issues' ? 'var(--color-error)' : 'transparent',
                        borderColor: status === 'has_issues' ? 'var(--color-error)' : 'var(--color-border)',
                        color: status === 'has_issues' ? '#ffffff' : 'var(--color-text-secondary)',
                        whiteSpace: 'nowrap',
                    }}
                    onClick={handleFlag}
                    disabled={loading.activeSection}
                    title="Flag Section"
                >
                    <AlertTriangle size={14} />
                    <span>Flag</span>
                </button>

                <button
                    className="btn btn-secondary"
                    style={{
                        padding: '6px 12px',
                        fontSize: '0.8rem',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text-secondary)',
                        whiteSpace: 'nowrap',
                    }}
                    onClick={() => setAiFixOpen(true)}
                    disabled={loading.activeSection}
                    title="Send this section's JSON + PDF pages to the AI for a proposed fix"
                >
                    <Sparkles size={14} />
                    <span>AI Fix</span>
                </button>
            </div>

            <div className="flex align-center gap-1" style={{ flexShrink: 0 }}>
                <button
                    className="btn btn-secondary btn-icon"
                    style={{ width: 32, height: 32 }}
                    onClick={() => navigateToSection(currentIndex - 1)}
                    disabled={!hasPrev || loading.activeSection}
                    title="Previous Section"
                >
                    <ArrowLeft size={14} />
                </button>

                <button
                    className="btn btn-secondary btn-icon"
                    style={{ width: 32, height: 32 }}
                    onClick={() => navigateToSection(currentIndex + 1)}
                    disabled={!hasNext || loading.activeSection}
                    title="Next Section"
                >
                    <ArrowRight size={14} />
                </button>
            </div>

            <AiFixPanel
                open={aiFixOpen}
                onClose={() => setAiFixOpen(false)}
                documentId={activeDocument.id}
                section={targetSection}
                onApplied={async () => {
                    // The approval created a new active version; refresh everything
                    // that renders the leaf or its status.
                    await fetchDocument(activeDocument.id);
                    await fetchSections(activeDocument.id);
                    await fetchSection(activeDocument.id, targetSection.id);
                }}
            />
        </div>
    );
};

export default ReviewToolbar;
