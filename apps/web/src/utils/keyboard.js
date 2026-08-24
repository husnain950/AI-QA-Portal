/** Whether a keystroke should be left to the focused control rather than handled
 * as a shortcut.
 *
 * There were four versions of this check across five call sites and they disagreed:
 * two looked at `document.activeElement` and two at `event.target`; two counted
 * `<select>` and two did not; two counted `contentEditable` and two did not. So `/`
 * focused the sidebar filter while you were typing in a `<select>`, and `[`/`]` paged
 * the PDF while you were typing in a rich-text field -- the shortcuts leaked into some
 * inputs and not others depending on which copy was watching.
 *
 * This is the union of all four: an editable control, whether identified by the event's
 * target or by what currently has focus.
 */
const EDITABLE = 'input, textarea, select';

export function isTypingTarget(event = null) {
    const candidates = [event?.target, document.activeElement];
    return candidates.some(
        (el) =>
            el &&
            (el.matches?.(EDITABLE) ||
                el.isContentEditable === true ||
                el.contentEditable === 'true'),
    );
}
