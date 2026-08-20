import { create } from 'zustand';
import { api } from '../utils/api';
import { useDocumentStore } from './documentStore';

export const useReviewStore = create((set, get) => ({
    annotations: [],
    globalAnnotations: [],
    viewMode: 'section', // 'section' | 'page'
    currentPage: 1,
    activeFootnoteId: null,

    fetchAnnotations: async (sectionId) => {
        try {
            const data = await api.get(`/sections/${sectionId}/annotations`);
            set({ annotations: data });
            return data;
        } catch (e) {
            console.error('Failed to fetch annotations', e);
            return [];
        }
    },

    fetchGlobalAnnotations: async (documentId) => {
        try {
            const data = await api.get(`/documents/${documentId}/annotations`);
            set({ globalAnnotations: data });
            return data;
        } catch (e) {
            console.error('Failed to fetch global annotations', e);
            return [];
        }
    },

    createAnnotation: async (sectionId, annotationData) => {
        try {
            const res = await api.post(`/sections/${sectionId}/annotations`, {
                highlighted_text: annotationData.highlightedText,
                start_offset: annotationData.startOffset,
                end_offset: annotationData.endOffset,
                issue_description: annotationData.issueDescription,
                severity: annotationData.severity,
                disposition: annotationData.disposition || 'open',
                footnote_id: annotationData.footnoteId || null,
                context_before: annotationData.contextBefore ?? null,
                context_after: annotationData.contextAfter ?? null
            });

            // Update annotations in store
            set((state) => ({ 
                annotations: [...state.annotations, res],
                globalAnnotations: [...state.globalAnnotations, res]
            }));

            // side effects: updates active section's review status
            const docStore = useDocumentStore.getState();
            if (docStore.activeSection && docStore.activeSection.id === sectionId) {
                docStore.fetchSection(docStore.activeDocument.id, sectionId);
                docStore.fetchSections(docStore.activeDocument.id);
            }
            return res;
        } catch (e) {
            console.error('Failed to create annotation', e);
            throw e;
        }
    },

    updateAnnotation: async (annotationId, updateData) => {
        try {
            const body = {};
            if (updateData.issueDescription !== undefined) {
                body.issue_description = updateData.issueDescription;
            }
            if (updateData.severity !== undefined) {
                body.severity = updateData.severity;
            }
            if (updateData.anchorStatus !== undefined) {
                body.anchor_status = updateData.anchorStatus;
            }
            if (updateData.disposition !== undefined) {
                body.disposition = updateData.disposition;
            }
            const res = await api.patch(`/annotations/${annotationId}`, body);

            set((state) => ({
                annotations: state.annotations.map(a => a.id === annotationId ? res : a),
                globalAnnotations: state.globalAnnotations.map(a => a.id === annotationId ? res : a)
            }));
            return res;
        } catch (e) {
            console.error('Failed to update annotation', e);
            throw e;
        }
    },

    deleteAnnotation: async (annotationId) => {
        try {
            const deleted = get().globalAnnotations.find(a => a.id === annotationId) || get().annotations.find(a => a.id === annotationId);
            
            await api.delete(`/annotations/${annotationId}`);
            
            set((state) => ({
                annotations: state.annotations.filter(a => a.id !== annotationId),
                globalAnnotations: state.globalAnnotations.filter(a => a.id !== annotationId)
            }));

            // side effects: refresh section and sidebar counts
            if (deleted) {
                const docStore = useDocumentStore.getState();
                docStore.fetchSection(docStore.activeDocument.id, deleted.section_id);
                docStore.fetchSections(docStore.activeDocument.id);
                docStore.fetchDocument(docStore.activeDocument.id);
            }
        } catch (e) {
            console.error('Failed to delete annotation', e);
            throw e;
        }
    },

    updateFootnoteStatus: async (footnoteId, status) => {
        try {
            const res = await api.patch(`/footnotes/${footnoteId}/status`, {
                review_status: status
            });
            
            const docStore = useDocumentStore.getState();
            
            // 1. Update activeSection if it contains the footnote
            const activeSection = docStore.activeSection;
            if (activeSection && activeSection.footnotes && activeSection.footnotes.some(f => f.id === footnoteId)) {
                const updatedFootnotes = activeSection.footnotes.map(fn => 
                    fn.id === footnoteId ? { ...fn, review_status: status } : fn
                );
                
                let newSectionStatus = activeSection.review_status;
                if (status === 'has_issues') {
                    newSectionStatus = 'has_issues';
                }

                useDocumentStore.setState({
                    activeSection: { 
                        ...activeSection, 
                        footnotes: updatedFootnotes,
                        review_status: newSectionStatus
                    }
                });
            }
            
            // 2. Update pageSections if they contain the footnote
            const pageSections = docStore.pageSections;
            if (pageSections && pageSections.length > 0) {
                useDocumentStore.setState({
                    pageSections: pageSections.map(s => {
                        if (s.footnotes && s.footnotes.some(f => f.id === footnoteId)) {
                            return {
                                ...s,
                                review_status: status === 'has_issues' ? 'has_issues' : s.review_status,
                                footnotes: s.footnotes.map(fn => fn.id === footnoteId ? { ...fn, review_status: status } : fn)
                            };
                        }
                        return s;
                    })
                });
            }

            // 3. Find the section ID of the footnote to update sidebar status
            let targetSectionId = null;
            if (activeSection && activeSection.footnotes && activeSection.footnotes.some(f => f.id === footnoteId)) {
                targetSectionId = activeSection.id;
            } else if (pageSections && pageSections.length > 0) {
                const foundSec = pageSections.find(s => s.footnotes && s.footnotes.some(f => f.id === footnoteId));
                if (foundSec) targetSectionId = foundSec.id;
            }

            if (targetSectionId && status === 'has_issues') {
                const sections = docStore.sections;
                useDocumentStore.setState({
                    sections: sections.map(s => s.id === targetSectionId ? { ...s, review_status: 'has_issues' } : s)
                });
            }
            
            if (docStore.activeDocument) {
                docStore.fetchDocument(docStore.activeDocument.id);
            }
            
            return res;
        } catch (e) {
            console.error('Failed to update footnote status', e);
            throw e;
        }
    },

    toggleAnnotationStatus: async (annotationId, currentStatus) => {
        const nextStatus = currentStatus === 'open' ? 'resolved' : 'open';
        try {
            const res = await api.patch(`/annotations/${annotationId}`, {
                status: nextStatus
            });
            
            // 1. Update globalAnnotations state
            set((state) => ({
                globalAnnotations: state.globalAnnotations.map(a => a.id === annotationId ? { ...a, status: nextStatus } : a)
            }));

            // 2. Update active annotations state (for the active section)
            set((state) => ({
                annotations: state.annotations.map(a => a.id === annotationId ? { ...a, status: nextStatus } : a)
            }));

            // 3. Side effects: update parent section status
            const docStore = useDocumentStore.getState();
            const activeSection = docStore.activeSection;
            
            // Re-fetch document metadata to keep stats in sync
            if (docStore.activeDocument) {
                docStore.fetchDocument(docStore.activeDocument.id);
                docStore.fetchSections(docStore.activeDocument.id);
                
                // If in page view, refresh page sections
                if (get().viewMode === 'page') {
                    docStore.fetchSectionsByPage(docStore.activeDocument.id, get().currentPage);
                }
            }
            
            // If the active section is the parent of the resolved annotation, refresh activeSection from API
            const targetAnnot = get().globalAnnotations.find(a => a.id === annotationId);
            if (targetAnnot) {
                if (activeSection && activeSection.id === targetAnnot.section_id) {
                    docStore.fetchSection(docStore.activeDocument.id, activeSection.id);
                }
            }
            
            return res;
        } catch (e) {
            console.error('Failed to toggle annotation status', e);
            throw e;
        }
    },

    setViewMode: (mode) => set({ viewMode: mode }),
    setCurrentPage: (page) => set({ currentPage: page })
}));
