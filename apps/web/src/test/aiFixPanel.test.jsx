import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../hooks/usePdfRenderer', () => ({
    usePdfDocument: () => ({ pdfDoc: null, loading: false, error: null, numPages: 0 }),
    usePdfPageRenderer: () => ({ loading: false, error: null, blank: false }),
}));

vi.mock('../utils/api', () => ({
    api: {
        getFileUrl: vi.fn((filename) => `/uploads/${filename || 'doc.pdf'}`),
    },
    aiFixApi: {
        models: vi.fn(),
        list: vi.fn(),
        approve: vi.fn(),
        reject: vi.fn(),
    },
}));

import AiFixPanel from '../components/review/AiFixPanel';
import { useAiFixStore } from '../stores/aiFixStore';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';

const section = {
    id: 'sec-1',
    section_code: '1',
    section_heading: 'Short title, extent and commencement',
    html_content: '<p>(1) This Act may be called the Federal Excise Act, 2005,</p>',
    start_page: 5,
    end_page: 5,
};

const parityProposal = {
    id: 'prop-1',
    section_id: 'sec-1',
    status: 'failed',
    error: 'HTML textContent and plain_text differ',
    model_name: 'kimi',
    instructions: 'restore subsections (2) and (3)',
    proposed: {
        html: '<ol class="subsection"><li>(1) This Act may be called the Federal Excise Act, 2005.</li><li>(2) It extends to the whole of Pakistan.</li></ol>',
        plain_text: '(1) This Act may be called the Federal Excise Act, 2005. (2) It extends to the whole of Pakistan.',
    },
    validation: [{
        level: 'error',
        code: 'html_plain_parity',
        message: 'HTML textContent and plain_text differ',
    }],
    diff: {
        plain_text_diff: ['+(2) It extends to the whole of Pakistan.'],
        stats: { chars_before: 10, chars_after: 89, footnotes_before: 0, footnotes_after: 0 },
    },
};

describe('AiFixPanel Approve & apply', () => {
    beforeEach(() => {
        useDocumentStore.setState({
            activeDocument: { id: 'doc-1', pdf_filename: 'doc.pdf' },
        });
        useReviewStore.setState({ annotations: [] });
        useUiStore.setState({ pushToast: vi.fn() });
    });

    it('enables Approve on a failed html_plain_parity proposal and applies it', async () => {
        const approve = vi.fn().mockResolvedValue({ version_no: 2 });
        const onApplied = vi.fn();
        const onClose = vi.fn();
        useAiFixStore.setState({
            proposals: [parityProposal],
            models: [{ id: 'kimi', label: 'kimi', vision: false }],
            defaultModel: 'kimi',
            modelsError: null,
            fetchModels: vi.fn().mockResolvedValue([]),
            fetchProposals: vi.fn().mockResolvedValue([parityProposal]),
            approve,
            reject: vi.fn(),
            requestFix: vi.fn(),
        });

        render(
            <AiFixPanel
                open
                documentId="doc-1"
                section={section}
                onClose={onClose}
                onApplied={onApplied}
            />,
        );

        const button = screen.getByRole('button', { name: /Approve & apply/i });
        expect(button).toBeEnabled();
        fireEvent.click(button);
        await waitFor(() => expect(approve).toHaveBeenCalledWith('prop-1'));
        await waitFor(() => expect(onApplied).toHaveBeenCalled());
        expect(onClose).toHaveBeenCalled();
    });

    it('keeps Approve disabled when the leaf has active content', async () => {
        const unsafe = {
            ...parityProposal,
            proposed: { html: '<script>alert(1)</script>', plain_text: 'x' },
            validation: [{
                level: 'error',
                code: 'unsafe_html',
                message: 'html contains active content (script/style/event handlers)',
            }],
        };
        useAiFixStore.setState({
            proposals: [unsafe],
            models: [],
            defaultModel: null,
            modelsError: null,
            fetchModels: vi.fn().mockResolvedValue([]),
            fetchProposals: vi.fn().mockResolvedValue([unsafe]),
            approve: vi.fn(),
            reject: vi.fn(),
            requestFix: vi.fn(),
        });

        render(
            <AiFixPanel
                open
                documentId="doc-1"
                section={section}
                onClose={vi.fn()}
            />,
        );

        expect(screen.getByRole('button', { name: /Approve & apply/i })).toBeDisabled();
    });
});
