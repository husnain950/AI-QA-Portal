import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setActiveFootnoteId = vi.fn();
const jumpToCite = vi.fn();

vi.mock('../hooks/useTextSelection', () => ({
    useTextSelection: () => ({ clearSelection: vi.fn() }),
}));

vi.mock('../stores/reviewStore', () => ({
    useReviewStore: () => ({
        annotations: [],
        createAnnotation: vi.fn(),
        fetchAnnotations: vi.fn(),
        updateFootnoteStatus: vi.fn(),
        setCurrentPage: vi.fn(),
        setActiveFootnoteId,
        jumpToCite,
        activeFootnoteId: null,
        citeJumpNonce: 0,
        footnoteJumpNonce: 0,
    }),
}));

vi.mock('../components/annotations/AnnotationPopover', () => ({
    default: () => null,
}));

import HtmlPanel from '../components/review/HtmlPanel';
import FootnotePanel from '../components/footnotes/FootnotePanel';
import { findFootnoteForCite, footnoteTextForCite } from '../utils/footnoteCite';

describe('findFootnoteForCite', () => {
    it('matches exact marker and dotted suffix forms', () => {
        const footnotes = [
            { id: 'fn-1', marker: '37.42', text: 'Inserted by Finance Act, 1988.' },
        ];
        expect(findFootnoteForCite('37.42', footnotes)?.id).toBe('fn-1');
        expect(findFootnoteForCite({ textContent: '37.42' }, footnotes)?.id).toBe('fn-1');
        expect(findFootnoteForCite('42', footnotes)?.id).toBe('fn-1');
        expect(findFootnoteForCite('99', footnotes)).toBeNull();
    });

    it('footnoteTextForCite still prefers data-footnote-text', () => {
        const cite = {
            getAttribute: (name) => (name === 'data-footnote-text' ? 'From title attr' : null),
            textContent: '37.42',
        };
        expect(footnoteTextForCite(cite, [
            { marker: '37.42', text: 'From footnotes array' },
        ])).toBe('From title attr');
    });
});

describe('footnote jump navigation', () => {
    beforeEach(() => {
        setActiveFootnoteId.mockClear();
        jumpToCite.mockClear();
        Element.prototype.scrollIntoView = vi.fn();
    });

    it('clicking a cite sets activeFootnoteId instead of opening a popup', () => {
        const { container } = render(
            <HtmlPanel
                section={{ id: '25B', plain_text: '25B. Omitted' }}
                sectionId="25B"
                htmlContent={
                    '<h4 class="section-heading">'
                    + '<sup class="cite" title="Inserted by Finance Act, 1988.">37.42</sup>'
                    + '[25B. Omitted]</h4>'
                }
                footnotes={[
                    {
                        id: 'fn-37-42',
                        marker: '37.42',
                        text: 'Inserted by Finance Act, 1988.',
                    },
                ]}
            />,
        );

        const cite = container.querySelector('sup.cite');
        expect(cite).toHaveAttribute('data-fn-marker', '37.42');
        expect(cite).toHaveAttribute('data-fn-id', 'fn-37-42');

        fireEvent.click(cite);

        expect(setActiveFootnoteId).toHaveBeenCalledWith('fn-37-42');
        expect(container.querySelector('#footnote-click-popup')).toBeNull();
        expect(container.querySelector('.fn-popover')).toBeNull();
    });

    it('renders an up-arrow that calls jumpToCite', () => {
        render(
            <FootnotePanel
                footnotes={[
                    {
                        id: 'fn-37-42',
                        marker: '37.42',
                        page: 37,
                        text: 'Inserted by Finance Act, 1988.',
                        review_status: 'pending',
                    },
                ]}
                annotations={[]}
            />,
        );

        const backBtn = screen.getByRole('button', {
            name: /Jump back to citation for marker 37\.42/,
        });
        fireEvent.click(backBtn);
        expect(jumpToCite).toHaveBeenCalledWith('fn-37-42');
    });
});
