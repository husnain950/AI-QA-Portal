import React from 'react';

/** Unified status chip. tone: neutral | accent | success | warning | danger | info | outline */
export default function StatusChip({ tone = 'neutral', children, icon = null, title, className = '' }) {
    return (
        <span className={`chip chip-${tone} ${className}`} title={title || undefined}>
            {icon}
            {children}
        </span>
    );
}
