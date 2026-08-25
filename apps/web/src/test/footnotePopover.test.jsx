import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../hooks/useTextSelection', () => ({
    useTextSelection: () => ({ clearSelection: vi.fn() }),
}));
vi.mock('../stores/reviewStore', () => ({
    useReviewStore: () => ({
        annotations: [],
        createAnnotation: vi.fn(),
        fetchAnnotations: vi.fn(),
    }),
}));
vi.mock('../components/annotations/AnnotationPopover', () => ({
    default: () => null,
}));
vi.mock('../components/footnotes/FootnotePanel', () => ({
    default: () => null,
}));

import HtmlPanel from '../components/review/HtmlPanel';
import { footnoteTextForCite, MISSING_NOTE } from '../utils/footnoteCite';

describe('footnote popover', () => {
    it('falls back to footnotes[] when the cite title is empty', () => {
        const cite = {
            getAttribute: (name) => (name === 'data-footnote-text' ? '' : null),
            textContent: '37.42',
        };
        const text = footnoteTextForCite(cite, [
            { marker: '37.42', text: 'Inserted by Finance Act, 1988 and Omitted by Finance Act, 2004.' },
        ]);
        expect(text).toMatch(/Inserted by Finance Act, 1988/);
    });

    it('returns empty when neither title nor footnotes[] have the note', () => {
        const cite = {
            getAttribute: () => '',
            textContent: '37.42',
        };
        expect(footnoteTextForCite(cite, [])).toBe('');
    });

    it('shows attached note text when hovering an empty-title cite', () => {
        const { container } = render(
            <HtmlPanel
                section={{ id: '25B', plain_text: '25B. Omitted' }}
                sectionId="25B"
                htmlContent={
                    '<h4 class="section-heading">'
                    + '<sup class="cite" title="">37.42</sup>[25B. Omitted]</h4>'
                }
                footnotes={[
                    {
                        marker: '37.42',
                        text: 'Inserted by Finance Act, 1988 and Omitted by Finance Act, 2004.',
                    },
                ]}
            />,
        );
        fireEvent.mouseEnter(container.querySelector('sup.cite'));
        expect(screen.getByText(/Footnote 37\.42/)).toBeInTheDocument();
        expect(screen.getByText(/Inserted by Finance Act, 1988/)).toBeInTheDocument();
    });

    it('shows a missing-note line when the cite has no body anywhere', () => {
        const { container } = render(
            <HtmlPanel
                section={{ id: '25B', plain_text: '25B. Omitted' }}
                sectionId="25B"
                htmlContent={
                    '<h4 class="section-heading">'
                    + '<sup class="cite" title="">37.42</sup>[25B. Omitted]</h4>'
                }
                footnotes={[]}
            />,
        );
        fireEvent.mouseEnter(container.querySelector('sup.cite'));
        expect(screen.getByText(MISSING_NOTE)).toBeInTheDocument();
    });
});
