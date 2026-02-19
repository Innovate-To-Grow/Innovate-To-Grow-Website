/**
 * Simple markdown renderer for basic formatting.
 * Converts **bold**, _italic_, and __underline__ to HTML.
 */

export function renderMarkdown(markdown: string): string {
  let html = markdown;

  // Escape HTML to prevent XSS
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Convert markdown to HTML
  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Italic: _text_
  html = html.replace(/_(.+?)_/g, '<em>$1</em>');

  // Underline: __text__
  html = html.replace(/__(.+?)__/g, '<u>$1</u>');

  // Convert line breaks
  html = html.replace(/\n/g, '<br />');

  return html;
}
