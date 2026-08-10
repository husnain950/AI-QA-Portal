import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Breadcrumbs from '../components/review/Breadcrumbs';

describe('Breadcrumbs schedule chrome', () => {
    it('labels schedule containers as Schedule when hierarchy_kind is schedule', () => {
        render(
            <Breadcrumbs
                section={{
                    chapter_code: 'THE FIRST SCHEDULE',
                    chapter_heading: 'RATES',
                    hierarchy_kind: 'schedule',
                    section_code: '1',
                    section_heading: 'Rate of tax',
                }}
            />,
        );

        expect(screen.getByText('Schedule')).toBeInTheDocument();
        expect(screen.queryByText('Chapter')).not.toBeInTheDocument();
    });

    it('falls back to Schedule via /\bschedule\b/i when hierarchy_kind is missing', () => {
        render(
            <Breadcrumbs
                section={{
                    chapter_code: 'I',
                    chapter_heading: 'THE SECOND SCHEDULE',
                    section_code: '2',
                    section_heading: 'Exempt goods',
                }}
            />,
        );

        expect(screen.getByText('Schedule')).toBeInTheDocument();
        expect(screen.queryByText('Chapter')).not.toBeInTheDocument();
    });

    it('keeps Chapter for ordinary chapter rows', () => {
        render(
            <Breadcrumbs
                section={{
                    chapter_code: 'CHAPTER I',
                    chapter_heading: 'PRELIMINARY',
                    hierarchy_kind: 'chapter',
                    section_code: '1',
                    section_heading: 'Short title',
                }}
            />,
        );

        expect(screen.getByText('Chapter')).toBeInTheDocument();
        expect(screen.queryByText('Schedule')).not.toBeInTheDocument();
    });
});
