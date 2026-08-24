import { useState, useEffect } from 'react';

/**
 * Characters kept either side of a highlight. They are what lets the backend re-find
 * an annotation when a new JSON version rewrites the leaf around it -- without them a
 * repeated phrase is ambiguous and the finding has to be flagged for a human instead.
 * Keep in step with CONTEXT_CHARS in backend/services/anchoring.py.
 */
export const CONTEXT_CHARS = 60;

export const contextAround = (element, start, end) => {
    const full = element?.textContent || '';
    return {
        contextBefore: full.slice(Math.max(0, start - CONTEXT_CHARS), start),
        contextAfter: full.slice(end, end + CONTEXT_CHARS),
    };
};

export const getSelectionCharacterOffsetsWithin = (element) => {
    let start = 0;
    let end = 0;
    const sel = window.getSelection();
    if (sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(element);
        preCaretRange.setEnd(range.startContainer, range.startOffset);
        start = preCaretRange.toString().length;
        end = start + range.toString().length;
    }
    return { start, end };
};

/**
 * Build the annotation payload from container textContent.
 *
 * Offsets from Range.toString() index this string, and the API validates against
 * the same coordinate system (HTML with tags stripped). Selection.toString().trim()
 * is a different string — it drops surrounding whitespace without moving start/end —
 * so the quote always comes from the slice, and trim shrinks the offsets inward.
 */
export const highlightFromOffsets = (element, start, end) => {
    const full = element?.textContent || '';
    let from = Math.max(0, start);
    let to = Math.min(full.length, end);
    if (to <= from) return null;
    const raw = full.slice(from, to);
    const lead = raw.length - raw.trimStart().length;
    const trail = raw.length - raw.trimEnd().length;
    from += lead;
    to -= trail;
    if (to <= from) return null;
    return {
        text: full.slice(from, to),
        start: from,
        end: to,
        ...contextAround(element, from, to),
    };
};

export const useTextSelection = (containerRef, onSelectionComplete) => {
    const [selectedText, setSelectedText] = useState('');
    const [selectionCoords, setSelectionCoords] = useState(null);
    const [offsets, setOffsets] = useState({ start: 0, end: 0 });

    useEffect(() => {
        const handleMouseUp = () => {
            const container = containerRef.current;
            if (!container) return;

            const selection = window.getSelection();
            if (!selection.rangeCount || selection.isCollapsed) {
                setSelectedText('');
                setSelectionCoords(null);
                return;
            }

            const range = selection.getRangeAt(0);

            if (!container.contains(range.commonAncestorContainer)) {
                return;
            }

            const { start, end } = getSelectionCharacterOffsetsWithin(container);
            const highlight = highlightFromOffsets(container, start, end);
            if (!highlight) return;

            const rect = range.getBoundingClientRect();
            const containerRect = container.getBoundingClientRect();

            const coords = {
                top: rect.bottom - containerRect.top + container.scrollTop + 8,
                left: rect.left - containerRect.left + container.scrollLeft + (rect.width / 2) - 160
            };

            setSelectedText(highlight.text);
            setOffsets({ start: highlight.start, end: highlight.end });
            setSelectionCoords(coords);

            if (onSelectionComplete) {
                onSelectionComplete({
                    text: highlight.text,
                    start: highlight.start,
                    end: highlight.end,
                    coords,
                    contextBefore: highlight.contextBefore,
                    contextAfter: highlight.contextAfter,
                });
            }
        };

        const handleMouseDown = () => {
            // Keep existing selection intact until mouseup
        };

        const container = containerRef.current;
        if (container) {
            container.addEventListener('mouseup', handleMouseUp);
            container.addEventListener('mousedown', handleMouseDown);
        }

        return () => {
            if (container) {
                container.removeEventListener('mouseup', handleMouseUp);
                container.removeEventListener('mousedown', handleMouseDown);
            }
        };
    }, [containerRef, onSelectionComplete]);

    const clearSelection = () => {
        window.getSelection().removeAllRanges();
        setSelectedText('');
        setSelectionCoords(null);
    };

    return { selectedText, selectionCoords, offsets, clearSelection };
};
