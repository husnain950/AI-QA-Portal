// Who the reviewer is now comes from the session, not from this browser.
//
// The name used to live in localStorage and was sent as X-Reviewer, so anyone could
// attribute a change to anyone. The server derives the actor from the session cookie and
// ignores the header; this module just caches the principal /api/auth/me returned so the
// UI can label things without asking again.

let currentUser = null;

export function getCurrentUser() {
    return currentUser;
}

export function setCurrentUser(user) {
    currentUser = user || null;
    return currentUser;
}

/** Display name for attribution labels; empty when signed out. */
export function getReviewerName() {
    if (!currentUser) return '';
    return currentUser.display_name || currentUser.email || '';
}

/** Role gate for UI affordances. The server enforces the same order. */
const RANK = { reader: 0, reviewer: 1, admin: 2 };
export function hasRole(required) {
    const held = RANK[currentUser?.role];
    return held !== undefined && held >= RANK[required];
}
