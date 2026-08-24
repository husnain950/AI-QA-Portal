/** Write `text` to the clipboard, falling back to a hidden textarea.
 *
 * The Clipboard API needs a secure context and a permission the browser may refuse;
 * `execCommand('copy')` needs neither. `HtmlPanel` carried this fallback in 60 lines of
 * its own while `CopyButton` -- which had none -- sat unused with zero importers, so the
 * fallback lives here and there is one copy path in the app.
 */
export async function writeToClipboard(text) {
    if (navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return;
        } catch {
            // Refused or unavailable; fall through to the textarea.
        }
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');   // no on-screen keyboard on mobile
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    const previouslyFocused = document.activeElement;
    try {
        textarea.select();
        textarea.setSelectionRange(0, 99999);  // iOS ignores select() alone
        if (!document.execCommand('copy')) throw new Error('execCommand returned false');
    } finally {
        document.body.removeChild(textarea);
        previouslyFocused?.focus?.();
    }
}
