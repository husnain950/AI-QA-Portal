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

            if (deleted) {
                await useDocumentStore.getState().refreshReviewData({
                    sectionId: deleted.section_id,
                });
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
            // This used to reach into useDocumentStore.setState() three separate times
            // to patch activeSection.footnotes, pageSections and sections by hand, then
            // refetch the document. The store that owns those slices knows how to patch
            // them; this only has to say what changed.
            const docStore = useDocumentStore.getState();
            docStore.patchFootnote(footnoteId, { review_status: status });
            await docStore.refreshReviewData();
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
            const setStatus = (a) => (a.id === annotationId ? { ...a, status: nextStatus } : a);
            set((state) => ({
                globalAnnotations: state.globalAnnotations.map(setStatus),
                annotations: state.annotations.map(setStatus),
            }));
            const target = get().globalAnnotations.find((a) => a.id === annotationId);
            await useDocumentStore.getState().refreshReviewData({
                sectionId: target?.section_id ?? null,
                page: get().viewMode === 'page' ? get().currentPage : null,
            });
            return res;
        } catch (e) {
            console.error('Failed to toggle annotation status', e);
            throw e;
        }
    },

    setViewMode: (mode) => set({ viewMode: mode }),
    setCurrentPage: (page) => set({ currentPage: page })
}));
