import React from 'react';
import { fireEvent, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useKeyboardNav } from '../hooks/useKeyboardNav';

describe('review keyboard navigation', () => {
    it('maps J and K to next and previous sections', () => {
        const onNextSection = vi.fn();
        const onPreviousSection = vi.fn();
        renderHook(() => useKeyboardNav({ onNextSection, onPreviousSection }));

        fireEvent.keyDown(window, { key: 'j' });
        fireEvent.keyDown(window, { key: 'K' });

        expect(onNextSection).toHaveBeenCalledOnce();
        expect(onPreviousSection).toHaveBeenCalledOnce();
    });

    it('does not navigate while typing', () => {
        const onNextSection = vi.fn();
        renderHook(() => useKeyboardNav({ onNextSection }));
        const input = document.createElement('input');
        document.body.appendChild(input);
        input.focus();

        fireEvent.keyDown(window, { key: 'j' });

        expect(onNextSection).not.toHaveBeenCalled();
        input.remove();
    });
});
