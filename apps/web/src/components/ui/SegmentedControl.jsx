import React from 'react';

/**
 * Compact toggle group. options: [{ value, label, icon, title }]
 */
export default function SegmentedControl({
    options,
    value,
    onChange,
    ariaLabel,
    size = 'sm',
    className = '',
}) {
    return (
        <div className={`ui-segmented ui-segmented-${size} ${className}`} role="group" aria-label={ariaLabel}>
            {options.map((opt) => (
                <button
                    key={opt.value}
                    type="button"
                    className={`ui-segmented-option ${value === opt.value ? 'active' : ''}`}
                    aria-pressed={value === opt.value}
                    title={opt.title || undefined}
                    onClick={() => onChange(opt.value)}
                >
                    {opt.icon || null}
                    {opt.label ? <span>{opt.label}</span> : null}
                </button>
            ))}
        </div>
    );
}
