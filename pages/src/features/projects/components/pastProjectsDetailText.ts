import DOMPurify from 'dompurify';

const RICH_DETAIL_ALLOWED_TAGS = ['br', 'div', 'p', 'b', 'strong', 'i', 'em', 'u', 'mark'];
const RICH_DETAIL_ALLOWED_ATTR: string[] = [];

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const hasHtmlMarkup = (value: string) => /<\/?(br|div|p|b|strong|i|em|u|mark|span|font)\b/i.test(value);

const convertHighlightStylesToMark = (html: string) => {
  if (typeof document === 'undefined') {
    return html;
  }

  const template = document.createElement('template');
  template.innerHTML = html;
  template.content.querySelectorAll('span, font').forEach((node) => {
    const style = (node.getAttribute('style') ?? '').toLowerCase();
    const hasHighlight = style.includes('background') || Boolean(node.getAttribute('bgcolor'));
    if (!hasHighlight) {
      return;
    }

    const mark = document.createElement('mark');
    while (node.firstChild) {
      mark.appendChild(node.firstChild);
    }
    node.replaceWith(mark);
  });

  return template.innerHTML;
};

export const sanitizePastProjectsDetailHtml = (html: string) =>
  DOMPurify.sanitize(convertHighlightStylesToMark(html), {
    ALLOWED_TAGS: RICH_DETAIL_ALLOWED_TAGS,
    ALLOWED_ATTR: RICH_DETAIL_ALLOWED_ATTR,
  });

export const plainTextToPastProjectsDetailHtml = (value: string) =>
  escapeHtml(value).replace(/\r\n|\r|\n/g, '<br>');

export const normalizePastProjectsDetailHtml = (value: string) =>
  sanitizePastProjectsDetailHtml(hasHtmlMarkup(value) ? value : plainTextToPastProjectsDetailHtml(value));

export const pastProjectsDetailHtmlToPlainText = (html: string) => {
  const sanitizedHtml = sanitizePastProjectsDetailHtml(html);

  if (typeof document === 'undefined') {
    return sanitizedHtml
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(div|p)>/gi, '\n')
      .replace(/<[^>]*>/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trimEnd();
  }

  const template = document.createElement('template');
  template.innerHTML = sanitizedHtml;
  template.content.querySelectorAll('br').forEach((node) => {
    node.replaceWith(document.createTextNode('\n'));
  });
  template.content.querySelectorAll('div, p').forEach((node) => {
    node.appendChild(document.createTextNode('\n'));
  });

  return (template.content.textContent ?? '').replace(/\u00a0/g, ' ').replace(/\n{3,}/g, '\n\n').trimEnd();
};

const createClipboardHtml = (html: string) =>
  `<!doctype html><html><body>${sanitizePastProjectsDetailHtml(html).replace(
    /<mark>/g,
    '<mark style="background-color:#fff3a3;color:inherit;">',
  )}</body></html>`;

export const copyPastProjectsDetailToClipboard = async (html: string) => {
  const sanitizedHtml = sanitizePastProjectsDetailHtml(html);
  const clipboardHtml = createClipboardHtml(sanitizedHtml);
  const plainText = pastProjectsDetailHtmlToPlainText(sanitizedHtml);

  if (navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([clipboardHtml], {type: 'text/html'}),
          'text/plain': new Blob([plainText], {type: 'text/plain'}),
        }),
      ]);
      return;
    } catch {
      // Fall back to plain text below when rich clipboard writes are unavailable.
    }
  }

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(plainText);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = plainText;
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
};
