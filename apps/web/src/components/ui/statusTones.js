/**
 * Tone and label maps for StatusChip.
 *
 * Kept out of StatusChip.jsx so that file exports a component and nothing else —
 * mixing constants into a component module breaks React Fast Refresh.
 */

export const REVIEW_STATUS_TONES = {
    approved: 'success',
    approved_inherited: 'success',
    has_issues: 'danger',
    flagged: 'danger',
    pending: 'neutral',
};

export const REVIEW_STATUS_LABELS = {
    approved: 'Approved',
    approved_inherited: 'Inherited',
    has_issues: 'Flagged',
    flagged: 'Flagged',
    pending: 'Pending',
};

export const TRIAGE_TONES = {
    new: 'accent',
    parse_bug: 'danger',
    source_defect: 'warning',
    deliberate: 'info',
    not_a_defect: 'neutral',
    fixed: 'success',
};
