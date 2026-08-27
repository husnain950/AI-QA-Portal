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
        setActiveFootnoteId: vi.fn(),
        activeFootnoteId: null,
        citeJumpNonce: 0,
        footnoteJumpNonce: 0,
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

    it('renders gazette title and recital blocks in the parsed HTML pane', () => {
        const { container } = render(
            <HtmlPanel
                section={{ id: 'preamble', plain_text: 'AN\nWHEREAS' }}
                sectionId="preamble"
                htmlContent={
                    '<h4 class="section-heading">11. Foreign Assets (Declaration and Repatriation) Act, 2018.—</h4>'
                    + '<p class="act-title"><strong>AN</strong></p>'
                    + '<p class="act-title"><strong>ACT</strong></p>'
                    + '<p class="act-long-title">to provide for declaration and repatriation of assets</p>'
                    + '<p class="recital">WHEREAS there is a large scale non-reporting;</p>'
                    + '<p class="enacting-formula">It is hereby enacted as follows:—</p>'
                }
                footnotes={[]}
            />,
        );

        expect(container.querySelector('h4.section-heading')).toHaveTextContent(
            '11. Foreign Assets (Declaration and Repatriation) Act, 2018.—',
        );
        expect(container.querySelectorAll('p.act-title')).toHaveLength(2);
        expect(container.querySelector('p.act-long-title')).toHaveTextContent(
            /to provide for declaration/,
        );
        expect(container.querySelector('p.recital')).toHaveTextContent(/^WHEREAS/);
        expect(container.querySelector('p.enacting-formula')).toHaveTextContent(
            /It is hereby enacted/,
        );
    });
});
