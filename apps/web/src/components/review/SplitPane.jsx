import React, { useRef, useState, useEffect } from 'react';
import { useUiStore } from '../../stores/uiStore';

const MIN_RATIO = 0.2;
const MAX_RATIO = 0.8;
const KEY_STEP = 0.04;

const clamp = (ratio) => Math.max(MIN_RATIO, Math.min(MAX_RATIO, ratio));

const SplitPane = ({ left, right }) => {
    const containerRef = useRef(null);
    const [isResizing, setIsResizing] = useState(false);
    const { splitRatio, setSplitRatio } = useUiStore();

    const startResize = (e) => {
        e.preventDefault();
        setIsResizing(true);
    };

    useEffect(() => {
        if (!isResizing) return;

        const handlePointerMove = (e) => {
            if (!containerRef.current) return;
            const containerRect = containerRef.current.getBoundingClientRect();
            const relativeX = e.clientX - containerRect.left;
            setSplitRatio(clamp(relativeX / containerRect.width));
        };

        const handlePointerUp = () => {
            setIsResizing(false);
        };

        document.addEventListener('pointermove', handlePointerMove);
        document.addEventListener('pointerup', handlePointerUp);
        document.addEventListener('pointercancel', handlePointerUp);

        return () => {
            document.removeEventListener('pointermove', handlePointerMove);
            document.removeEventListener('pointerup', handlePointerUp);
            document.removeEventListener('pointercancel', handlePointerUp);
        };
    }, [isResizing, setSplitRatio]);

    const handleKeyDown = (e) => {
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            setSplitRatio(clamp(splitRatio - KEY_STEP));
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            setSplitRatio(clamp(splitRatio + KEY_STEP));
        } else if (e.key === 'Home') {
            e.preventDefault();
            setSplitRatio(MIN_RATIO);
        } else if (e.key === 'End') {
            e.preventDefault();
            setSplitRatio(MAX_RATIO);
        }
    };

    return (
        <div ref={containerRef} className="split-pane">
            <div className="panel" style={{ width: `${splitRatio * 100}%`, minWidth: '20%', maxWidth: '80%' }}>
                {left}
            </div>
            <div
                className={`resizer-handle ${isResizing ? 'active' : ''}`}
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize panels"
                aria-valuenow={Math.round(splitRatio * 100)}
                aria-valuemin={Math.round(MIN_RATIO * 100)}
                aria-valuemax={Math.round(MAX_RATIO * 100)}
                tabIndex={0}
                title="Drag to resize · double-click to reset · arrow keys when focused"
                onPointerDown={startResize}
                onDoubleClick={() => setSplitRatio(0.5)}
                onKeyDown={handleKeyDown}
            />
            <div className="panel" style={{ flex: 1, minWidth: '20%', maxWidth: '80%' }}>
                {right}
            </div>
        </div>
    );
};

export default SplitPane;
