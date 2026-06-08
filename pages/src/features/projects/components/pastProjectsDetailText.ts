import DOMPurify from 'dompurify';
import type {ProjectGridRow} from './projectGrid';

const detailValue = (value: string) => value.trim() || 'N/A';
const PROJECT_DETAIL_SEPARATOR = '\n\n------------------------------\n\n';
const RICH_DETAIL_ALLOWED_TAGS = ['br', 'div', 'p', 'b', 'strong', 'i', 'em', 'u', 'mark'];
const RICH_DETAIL_ALLOWED_ATTR: string[] = [];

const formatClassTeam = (row: ProjectGridRow) => {
  const parts = [row.class_code, row.team_number].map((value) => value.trim()).filter(Boolean);
  return parts.length ? parts.join(' / ') : 'N/A';
};

export const createPastProjectsDetailText = (rows: ProjectGridRow[]) =>
  rows
    .map((row, index) =>
      [
        `Project ${index + 1}`,
        `Year-Semester: ${detailValue(row.semester_label)}`,
        `Class / Team#: ${formatClassTeam(row)}`,
        `Team Name: ${detailValue(row.team_name)}`,
        `Project Title: ${detailValue(row.project_title)}`,
        `Organization: ${detailValue(row.organization)}`,
        `Industry: ${detailValue(row.industry)}`,
        `Students: ${detailValue(row.student_names)}`,
        `Abstract: ${detailValue(row.abstract)}`,
      ].join('\n'),
    )
    .join(PROJECT_DETAIL_SEPARATOR);

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

export const createPastProjectsDetailHtml = (rows: ProjectGridRow[]) =>
  plainTextToPastProjectsDetailHtml(createPastProjectsDetailText(rows));

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
