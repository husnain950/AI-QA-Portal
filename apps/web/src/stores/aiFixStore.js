import { create } from 'zustand';
import { aiFixApi } from '../utils/api';

/**
 * AI fix proposals for the document under review. One fetch per document load
 * keeps the "AI fixed" badge cheap; mutations update the cache in place.
 */
export const useAiFixStore = create((set, get) => ({
    documentId: null,
    proposals: [],
    models: [],
    defaultModel: null,

    fetchModels: async () => {
        if (get().models.length) return get().models;
        try {
            const data = await aiFixApi.models();
            set({ models: data.models, defaultModel: data.default });
            return data.models;
        } catch (e) {
            console.error('Failed to fetch AI fix models', e);
            return [];
        }
    },

    fetchProposals: async (documentId) => {
        try {
            const data = await aiFixApi.list(documentId);
            set({ documentId, proposals: data });
            return data;
        } catch (e) {
            console.error('Failed to fetch AI fix proposals', e);
            set({ documentId, proposals: [] });
            return [];
        }
    },

    requestFix: async (documentId, sectionId, instructions, modelName) => {
        const proposal = await aiFixApi.request(
            documentId, sectionId, instructions, modelName,
        );
        set((state) => ({ proposals: [proposal, ...state.proposals] }));
        return proposal;
    },

    approve: async (proposalId) => {
        const result = await aiFixApi.approve(proposalId);
        set((state) => ({
            proposals: state.proposals.map((proposal) =>
                proposal.id === proposalId
                    ? { ...proposal, status: 'approved' }
                    : proposal,
            ),
        }));
        return result;
    },

    reject: async (proposalId) => {
        const updated = await aiFixApi.reject(proposalId);
        set((state) => ({
            proposals: state.proposals.map((proposal) =>
                proposal.id === proposalId ? updated : proposal,
            ),
        }));
        return updated;
    },
}));
