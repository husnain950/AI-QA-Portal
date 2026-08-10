import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({
    api: {
        get: vi.fn(async () => []),
        patch: vi.fn(async () => ({})),
        delete: vi.fn(async () => ({})),
    },
}));

import Sidebar from '../components/layout/Sidebar';
import { useDocumentStore } from '../stores/documentStore';
import { useReviewStore } from '../stores/reviewStore';
import { useUiStore } from '../stores/uiStore';

describe('large TOC filtering', () => {
    beforeEach(() => {
        const sections = Array.from({ length: 1200 }, (_, index) => ({
            id: `section-${index}`,
            section_code: String(index + 1),
            section_heading: index === 1199 ? 'Needle provision' : `Provision ${index}`,
            chapter_code: `Chapter ${Math.floor(index / 100)}`,
            chapter_heading: 'General',
            review_status: 'pending',
            annotation_count: 0,
            start_page: index + 1,
        }));
        useDocumentStore.setState({
            sections,
            activeSection: sections[0],
            searchResults: [],
            loading: { search: false },
        });
        useReviewStore.setState({
            globalAnnotations: [],
            viewMode: 'section',
        });
        useUiStore.setState({ sidebarTab: 'toc' });
    });

    it('shows the visible count and only matching section nodes', () => {
        render(
            <MemoryRouter>
                <Sidebar documentId="document-1" />
            </MemoryRouter>,
        );

        fireEvent.change(screen.getByRole('searchbox', { name: 'Filter sections' }), {
            target: { value: 'needle' },
        });

        expect(screen.getByText('1 sections')).toBeInTheDocument();
        expect(screen.getByText(/Needle provision/)).toBeInTheDocument();
        expect(screen.queryByText(/Provision 500$/)).not.toBeInTheDocument();
    });

    it('skips orphan blank chapter headers and does not hard-truncate labels', () => {
        useDocumentStore.setState({
            sections: [
                {
                    id: 'sec-blank-chapter',
                    section_code: '1',
                    section_heading: 'Short title, extent and commencement of this Act',
                    chapter_code: '',
                    chapter_heading: '',
                    review_status: 'pending',
                    annotation_count: 0,
                    start_page: 1,
                },
                {
                    id: 'sec-part-leaf',
                    section_code: 'PART I',
                    section_heading: '] THE GAZETTE OF PAKISTAN, EXTRA.',
                    chapter_code: '',
                    chapter_heading: '',
                    review_status: 'pending',
                    annotation_count: 0,
                    start_page: 2,
                },
            ],
            activeSection: null,
            searchResults: [],
            loading: { search: false },
        });
        useUiStore.setState({ sidebarTab: 'toc' });

        const { container } = render(
            <MemoryRouter>
                <Sidebar documentId="document-1" />
            </MemoryRouter>,
        );

        expect(container.querySelector('.toc-node.level-chapter')).toBeNull();
        expect(
            screen.getByText(
                'Section 1: Short title, extent and commencement of this Act',
            ),
        ).toBeInTheDocument();
        expect(screen.getByText('PART I')).toBeInTheDocument();
        expect(screen.queryByText(/THE GAZETTE/)).not.toBeInTheDocument();
    });
});
