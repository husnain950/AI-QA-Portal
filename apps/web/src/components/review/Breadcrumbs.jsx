import React from 'react';
import { ChevronRight } from 'lucide-react';
import { cleanHeading, hierarchyTypeLabel } from '../../utils/tocLabels';

const Breadcrumbs = ({ section }) => {
    if (!section) return null;

    const {
        chapter_code,
        chapter_heading,
        part_code,
        part_heading,
        division_code,
        division_heading,
        section_code,
        section_heading,
        hierarchy_kind,
    } = section;

    const items = [];

    const formatBreadcrumb = (type, code) => {
        if (!code) return '';
        const cleanCode = code.trim();
        if (type === 'Section') {
            if (cleanCode.toLowerCase().startsWith('section') || cleanCode.toLowerCase().startsWith('sec')) {
                return cleanCode;
            }
            return `Section ${cleanCode}`;
        }
        if (cleanCode.toLowerCase().startsWith(type.toLowerCase())) {
            return cleanCode;
        }
        return `${type} ${cleanCode}`;
    };

    if (chapter_code && chapter_code.trim()) {
        const type = hierarchyTypeLabel(hierarchy_kind, chapter_code, chapter_heading);
        const formatted = formatBreadcrumb(type, chapter_code);
        items.push({
            type,
            code: formatted,
            heading: cleanHeading(chapter_heading),
        });
    }

    if (part_code && part_code.trim()) {
        const formatted = formatBreadcrumb('Part', part_code);
        items.push({
            type: 'Part',
            code: formatted,
            heading: cleanHeading(part_heading),
        });
    }

    if (division_code && division_code.trim()) {
        const formatted = formatBreadcrumb('Division', division_code);
        items.push({
            type: 'Division',
            code: formatted,
            heading: cleanHeading(division_heading),
        });
    }

    if (section_code && section_code.trim()) {
        const formatted = formatBreadcrumb('Section', section_code);
        items.push({
            type: 'Section',
            code: formatted,
            heading: cleanHeading(section_heading),
        });
    }

    if (items.length === 0) return null;

    const abbrs = {
        Chapter: 'Chapter|Ch',
        Schedule: 'Schedule|Sch',
        Part: 'Part|Pt',
        Division: 'Division|Div',
        Section: 'Section|Sec'
    };

    return (
        <nav className="breadcrumbs-container" aria-label="Section hierarchy" onClick={(e) => e.stopPropagation()}>
            {items.map((item, idx) => {
                const regexStr = `^(?:${abbrs[item.type] || item.type})\\s*`;
                const displayCode = item.code
                    .replace(new RegExp(regexStr, 'i'), '')
                    .replace(/^[-_:\s]+/, '')
                    .trim();

                return (
                    <React.Fragment key={idx}>
                        {idx > 0 && <ChevronRight size={12} className="breadcrumb-separator" aria-hidden="true" />}
                        <div 
                            className="breadcrumb-item" 
                            title={`${item.code}${item.heading ? ': ' + item.heading : ''}`}
                        >
                            <span className="breadcrumb-type">{item.type}</span>
                            <span className="breadcrumb-code">{displayCode}</span>
                            {item.heading && (
                                <span className="breadcrumb-heading">
                                    &middot; {item.heading}
                                </span>
                            )}
                        </div>
                    </React.Fragment>
                );
            })}
        </nav>
    );
};

export default Breadcrumbs;
