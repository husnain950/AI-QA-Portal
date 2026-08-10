import React, { useRef, useState, useEffect } from 'react';
import { useUiStore } from '../../stores/uiStore';

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

        const handleMouseMove = (e) => {
            if (!containerRef.current) return;
            const containerRect = containerRef.current.getBoundingClientRect();
            const relativeX = e.clientX - containerRect.left;
            const ratio = relativeX / containerRect.width;
            
            // Constrain ratio between 20% and 80%
            const boundedRatio = Math.max(0.2, Math.min(0.8, ratio));
            setSplitRatio(boundedRatio);
        };

        const handleMouseUp = () => {
            setIsResizing(false);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);

        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isResizing, setSplitRatio]);

    return (
        <div ref={containerRef} className="split-pane">
            <div className="panel" style={{ width: `${splitRatio * 100}%`, minWidth: '20%', maxWidth: '80%' }}>
                {left}
            </div>
            <div 
                className={`resizer-handle ${isResizing ? 'active' : ''}`}
                onMouseDown={startResize}
            />
            <div className="panel" style={{ flex: 1, minWidth: '20%', maxWidth: '80%' }}>
                {right}
            </div>
        </div>
    );
};

export default SplitPane;
