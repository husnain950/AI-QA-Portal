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

describe('Plain Text view', () => {
    it('shows punctuation-faithful extracted text separately from HTML', () => {
        render(
            <HtmlPanel
                section={{
                    id: 'section-1',
                    plain_text: 'Tax, duty: and levy.',
                }}
                sectionId="section-1"
                htmlContent="<p>Rendered <strong>HTML</strong></p>"
                footnotes={[]}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: /Plain Text/ }));

        expect(screen.getByText('Tax, duty: and levy.')).toBeInTheDocument();
        expect(screen.getByText('Extracted Plain Text')).toBeInTheDocument();
    });
});
