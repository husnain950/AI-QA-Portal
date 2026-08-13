import React from 'react';

/** Consistent empty/zero states: icon, headline, supporting copy, actions. */
export default function EmptyState({ icon = null, title, message = null, children = null, compact = false }) {
    return (
        <div className={`ui-empty-state ${compact ? 'is-compact' : ''}`}>
            {icon ? <div className="ui-empty-state-icon">{icon}</div> : null}
            {title ? <h3 className="ui-empty-state-title">{title}</h3> : null}
            {message ? <p className="ui-empty-state-message">{message}</p> : null}
            {children ? <div className="ui-empty-state-actions">{children}</div> : null}
        </div>
    );
}
