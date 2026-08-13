import React from 'react';

/** Shimmering placeholder block for loading states. */
export default function Skeleton({ width, height = 14, className = '', style = {} }) {
    return (
        <span
            className={`ui-skeleton ${className}`}
            style={{ width, height, ...style }}
            aria-hidden="true"
        />
    );
}
