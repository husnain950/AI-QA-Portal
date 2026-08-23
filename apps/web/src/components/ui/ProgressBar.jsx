import React from 'react';

/** A completion bar. Five identical copies of this markup existed across the pages.
 *
 * `aria-hidden` is the caller's choice: where the percentage is also rendered as text
 * beside the bar it is decorative, and where it is not, it should be announced.
 */
export default function ProgressBar({ pct, ariaHidden = false, label = null }) {
    const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
    return (
        <span
            className="progress-bar"
            aria-hidden={ariaHidden || undefined}
            role={ariaHidden ? undefined : 'progressbar'}
            aria-valuenow={ariaHidden ? undefined : clamped}
            aria-valuemin={ariaHidden ? undefined : 0}
            aria-valuemax={ariaHidden ? undefined : 100}
            aria-label={ariaHidden ? undefined : (label || 'completion')}
        >
            <span
                className={`progress-bar-fill ${clamped === 100 ? 'is-complete' : ''}`}
                style={{ width: `${clamped}%` }}
            />
        </span>
    );
}
