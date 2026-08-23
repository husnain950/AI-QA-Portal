import React, { useEffect, useRef, useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { writeToClipboard } from '../../utils/clipboard';

/** Copy-to-clipboard button with inline confirmation feedback. */
export default function CopyButton({
    getText,
    label = null,
    title = 'Copy to clipboard',
    copiedLabel = 'Copied',
    className = 'btn btn-ghost btn-icon',
    size = 14,
    onError = null,
}) {
    const [copied, setCopied] = useState(false);
    const timerRef = useRef(null);

    useEffect(() => () => clearTimeout(timerRef.current), []);

    const handleCopy = async (e) => {
        e.stopPropagation();
        const text = typeof getText === 'function' ? getText() : getText;
        if (!text) return;
        try {
            await writeToClipboard(text);
            setCopied(true);
            clearTimeout(timerRef.current);
            timerRef.current = setTimeout(() => setCopied(false), 1600);
        } catch (err) {
            onError?.(err);
        }
    };

    return (
        <button
            type="button"
            className={className}
            onClick={handleCopy}
            title={copied ? copiedLabel : title}
            aria-label={copied ? copiedLabel : title}
        >
            {copied ? <Check size={size} style={{ color: 'var(--color-success)' }} /> : <Copy size={size} />}
            {label ? <span>{copied ? copiedLabel : label}</span> : null}
        </button>
    );
}
