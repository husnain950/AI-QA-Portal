import React from 'react';
import { ChevronRight } from 'lucide-react';
import { leafHierarchyItems } from '../../utils/tocLabels';

const Breadcrumbs = ({ section }) => {
    if (!section) return null;

    const items = leafHierarchyItems(section);
    if (items.length === 0) return null;

    return (
        <nav className="breadcrumbs-container" aria-label="Section hierarchy" onClick={(e) => e.stopPropagation()}>
            {items.map((item, idx) => (
                <React.Fragment key={idx}>
                    {idx > 0 && <ChevronRight size={12} className="breadcrumb-separator" aria-hidden="true" />}
                    <div
                        className="breadcrumb-item"
                        title={`${item.code}${item.heading ? ': ' + item.heading : ''}`}
                    >
                        <span className="breadcrumb-type">{item.type}</span>
                        <span className="breadcrumb-code">{item.displayCode}</span>
                        {item.heading && (
                            <span className="breadcrumb-heading">
                                &middot; {item.heading}
                            </span>
                        )}
                    </div>
                </React.Fragment>
            ))}
        </nav>
    );
};

export default Breadcrumbs;
