import React, { useCallback, useEffect, useState } from 'react';
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
import { isTypingTarget } from '../../utils/keyboard';

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
    const isPrimaryToolbar = sectionProp === null;

    const aiFixed = targetSection ? hasApprovedFix(aiProposals, targetSection.id) : false;

    const currentIndex = targetSection
        ? sections.findIndex((s) => s.id === targetSection.id)
        : -1;
    const hasPrev = currentIndex > 0;
    const hasNext = currentIndex >= 0 && currentIndex < sections.length - 1;
    const qualityFlagsValue = targetSection?.quality_flags;
    // Approve gate: any flag (incl. page_range_out_of_bounds) needs confirm.
    const needsQualityOverride = targetSection ? hasAnyQualityFlags(targetSection.quality_flags) : false;
    const status = targetSection?.review_status;

    const navigateToSection = useCallback((index) => {
        if (index < 0 || index >= sections.length) return;
        const targetSec = sections[index];
        navigate(`/review/${activeDocument.id}/${targetSec.id}`);
    }, [sections, navigate, activeDocument?.id]);

    const handleApprove = useCallback(async () => {
        if (!targetSection || !activeDocument) return;
        if (needsQualityOverride) {
            const listed = formatQualityFlagList(qualityFlagsValue).map((r) => `• ${r}`).join('\n');
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
    }, [
        targetSection, activeDocument, needsQualityOverride, qualityFlagsValue,
        confirmDialog, updateSectionStatus, hasNext, navigateToSection, currentIndex, pushToast,
    ]);

    const handleFlag = useCallback(async () => {
        if (!targetSection || !activeDocument) return;
        try {
            await updateSectionStatus(activeDocument.id, targetSection.id, 'has_issues');
        } catch (e) {
            pushToast({ type: 'error', message: `Failed to update status: ${e.message}` });
        }
    }, [targetSection, activeDocument, updateSectionStatus, pushToast]);

    const handlePending = useCallback(async () => {
        if (!targetSection || !activeDocument) return;
        try {
            await updateSectionStatus(activeDocument.id, targetSection.id, 'pending');
        } catch (e) {
            pushToast({ type: 'error', message: `Failed to update status: ${e.message}` });
        }
    }, [targetSection, activeDocument, updateSectionStatus, pushToast]);

    // Status shortcuts (A approve / F flag / P pending) for the section-view toolbar.
    useEffect(() => {
        if (!isPrimaryToolbar || !targetSection) return undefined;
        const onKey = (e) => {
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            if (isTypingTarget(e)) return;
            // Ignore while a dialog/modal is open (confirm, AI fix, palette…).
            if (aiFixOpen || document.querySelector('dialog[open], .cp-overlay')) return;
            if (e.key === 'a' || e.key === 'A') {
                e.preventDefault();
                handleApprove();
            } else if (e.key === 'f' || e.key === 'F') {
                e.preventDefault();
                handleFlag();
            } else if (e.key === 'p' || e.key === 'P') {
                e.preventDefault();
                handlePending();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isPrimaryToolbar, targetSection, aiFixOpen, handleApprove, handleFlag, handlePending]);

    if (!targetSection || !activeDocument) return null;

    const isApproved = status === 'approved' || status === 'approved_inherited';

    return (
        <div className="review-toolbar">
            <div className="review-toolbar-status">
                {loading.activeSection ? (
                    <Loader2 className="animate-spin" size={14} style={{ color: 'var(--color-accent)' }} />
                ) : (
                    <>
                        <span className="review-toolbar-label">Status</span>
                        <span
                            className={`badge badge-${status === 'has_issues' ? 'flagged' : status === 'approved_inherited' ? 'approved' : status}`}
                        >
                            {status === 'has_issues' ? 'flagged' : status === 'approved_inherited' ? 'inherited' : status}
                        </span>
                        {aiFixed && (
                            <span
                                className="chip chip-accent"
                                title="An approved AI fix is applied to this section"
                            >
                                <Sparkles size={11} /> AI fixed
                            </span>
                        )}
                    </>
                )}
            </div>

            <div className="review-toolbar-actions">
                <button
                    className={`btn btn-sm btn-secondary ${status === 'pending' ? 'is-selected' : ''}`}
                    onClick={handlePending}
                    disabled={loading.activeSection}
                    title="Mark section as pending (P)"
                >
                    <Clock size={14} />
                    <span>Pending</span>
                </button>

                <button
                    className={`btn btn-sm ${isApproved ? 'review-status-approved' : 'btn-secondary'}`}
                    onClick={handleApprove}
                    disabled={loading.activeSection}
                    title="Approve section & move next (A)"
                >
                    <Check size={14} />
                    <span>Approve</span>
                </button>

                <button
                    className={`btn btn-sm ${status === 'has_issues' ? 'review-status-flagged' : 'btn-secondary'}`}
                    onClick={handleFlag}
                    disabled={loading.activeSection}
                    title="Flag section (F)"
                >
                    <AlertTriangle size={14} />
                    <span>Flag</span>
                </button>

                <span className="review-toolbar-divider" aria-hidden="true" />

                <button
                    className="btn btn-sm btn-secondary"
                    onClick={() => setAiFixOpen(true)}
                    disabled={loading.activeSection}
                    title="Send this section's JSON + PDF pages to the AI for a proposed fix"
                >
                    <Sparkles size={14} />
                    <span>AI Fix</span>
                </button>
            </div>

            <div className="review-toolbar-nav">
                <button
                    className="btn btn-secondary btn-icon"
                    onClick={() => navigateToSection(currentIndex - 1)}
                    disabled={!hasPrev || loading.activeSection}
                    title="Previous section (K)"
                    aria-label="Previous section"
                >
                    <ArrowLeft size={14} />
                </button>

                <button
                    className="btn btn-secondary btn-icon"
                    onClick={() => navigateToSection(currentIndex + 1)}
                    disabled={!hasNext || loading.activeSection}
                    title="Next section (J)"
                    aria-label="Next section"
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
