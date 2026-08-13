import React, { useRef, useState } from 'react';
import { Copy, Check } from 'lucide-react';

/** Copy-to-clipboard button with inline confirmation feedback. */
export default function CopyButton({
    getText,
    label = null,
    title = 'Copy to clipboard',
    className = 'btn btn-ghost btn-icon',
    size = 14,
}) {
    const [copied, setCopied] = useState(false);
    const timerRef = useRef(null);

    const handleCopy = async (e) => {
        e.stopPropagation();
        try {
            const text = typeof getText === 'function' ? getText() : getText;
            await navigator.clipboard.writeText(text ?? '');
            setCopied(true);
            clearTimeout(timerRef.current);
            timerRef.current = setTimeout(() => setCopied(false), 1600);
        } catch {
            // Clipboard unavailable (permissions/insecure context) — nothing to do.
        }
    };

    return (
        <button
            type="button"
            className={className}
            onClick={handleCopy}
            title={copied ? 'Copied' : title}
            aria-label={copied ? 'Copied' : title}
        >
            {copied ? <Check size={size} style={{ color: 'var(--color-success)' }} /> : <Copy size={size} />}
            {label ? <span>{copied ? 'Copied' : label}</span> : null}
        </button>
    );
}
