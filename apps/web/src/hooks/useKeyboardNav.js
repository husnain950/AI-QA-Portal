import { useEffect } from 'react';

export const useKeyboardNav = ({ 
    onArrowLeft, 
    onArrowRight, 
    onPreviousSection,
    onNextSection,
    onEscape 
}) => {
    useEffect(() => {
        const handleKeyDown = (e) => {
            // Do not trigger navigation if the user is typing in a form input or textarea
            const activeEl = document.activeElement;
            const isTyping = activeEl && (
                activeEl.tagName === 'INPUT' || 
                activeEl.tagName === 'TEXTAREA' || 
                activeEl.contentEditable === 'true'
            );
            if (isTyping) return;

            if (e.key === 'ArrowLeft' && onArrowLeft) {
                e.preventDefault();
                onArrowLeft();
            } else if (e.key === 'ArrowRight' && onArrowRight) {
                e.preventDefault();
                onArrowRight();
            } else if ((e.key === 'k' || e.key === 'K') && onPreviousSection) {
                e.preventDefault();
                onPreviousSection();
            } else if ((e.key === 'j' || e.key === 'J') && onNextSection) {
                e.preventDefault();
                onNextSection();
            } else if (e.key === 'Escape' && onEscape) {
                e.preventDefault();
                onEscape();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [onArrowLeft, onArrowRight, onPreviousSection, onNextSection, onEscape]);
};
