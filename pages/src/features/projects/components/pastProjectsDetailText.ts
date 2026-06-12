import DOMPurify from 'dompurify';
import {getPastProjectDetailUrl, type ProjectGridRow} from './projectGrid';

const RICH_DETAIL_ALLOWED_TAGS = ['br', 'div', 'p', 'b', 'strong', 'i', 'em', 'u', 'mark', 'a'];
const RICH_DETAIL_ALLOWED_ATTR = ['href', 'data-past-project-note-curation'];
const PAST_PROJECT_NOTE_CURATION_ATTR = 'data-past-project-note-curation';
const PAST_PROJECT_NOTE_CURATION_VALUE = 'project-summary';
const PAST_PROJECT_NOTE_CURATION_SELECTOR = `div[${PAST_PROJECT_NOTE_CURATION_ATTR}="${PAST_PROJECT_NOTE_CURATION_VALUE}"]`;

export const PAST_PROJECT_NOTE_INSERT_FIELDS = [
  {key: 'project_label', label: 'Project label'},
  {key: 'semester_label', label: 'Year-Semester'},
  {key: 'class_team', label: 'Class / Team#'},
  {key: 'team_name', label: 'Team Name'},
  {key: 'project_title', label: 'Project Title'},
  {key: 'individual_link', label: 'Individual Link'},
  {key: 'organization', label: 'Organization'},
  {key: 'industry', label: 'Industry'},
  {key: 'students', label: 'Students'},
  {key: 'abstract', label: 'Abstract'},
] as const;

export type PastProjectNoteInsertField = (typeof PAST_PROJECT_NOTE_INSERT_FIELDS)[number]['key'];

export interface PastProjectNoteInsertOptions {
  excludedFields?: readonly PastProjectNoteInsertField[];
}

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const hasHtmlMarkup = (value: string) => /<\/?(br|div|p|b|strong|i|em|u|mark|a|span|font)\b/i.test(value);

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

const fieldLine = (label: string, value: string) =>
  value.trim() ? `<div><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value.trim())}</div>` : '';

const individualProjectHref = (row: ProjectGridRow) => {
  if (!row.id) {
    return '';
  }
  return getPastProjectDetailUrl(row.id);
};

const projectInsertHtml = (row: ProjectGridRow, index: number, excludedFields: Set<PastProjectNoteInsertField>) => {
  const href = individualProjectHref(row);
  const include = (field: PastProjectNoteInsertField, html: string) => (excludedFields.has(field) ? '' : html);
  return [
    include('project_label', `<div><strong>Project ${index + 1}</strong></div>`),
    include('semester_label', fieldLine('Year-Semester', row.semester_label)),
    include(
      'class_team',
      fieldLine(
        'Class / Team#',
        [row.class_code, row.team_number].map((value) => value.trim()).filter(Boolean).join(' / '),
      ),
    ),
    include('team_name', fieldLine('Team Name', row.team_name)),
    include('project_title', fieldLine('Project Title', row.project_title)),
    include(
      'individual_link',
      href ? `<div><strong>Individual Link:</strong> <a href="${escapeHtml(href)}">${escapeHtml(href)}</a></div>` : '',
    ),
    include('organization', fieldLine('Organization', row.organization)),
    include('industry', fieldLine('Industry', row.industry)),
    include('students', fieldLine('Students', row.student_names)),
    include('abstract', fieldLine('Abstract', row.abstract)),
  ]
    .filter(Boolean)
    .join('');
};

export const buildPastProjectsNoteInsertHtml = (
  rows: ProjectGridRow[],
  options: PastProjectNoteInsertOptions = {},
) => {
  const excludedFields = new Set(options.excludedFields ?? []);
  const projectHtml = rows
    .map((row, index) => projectInsertHtml(row, index, excludedFields))
    .filter(Boolean)
    .join('<div>------------------------------</div>');

  if (!projectHtml) {
    return '';
  }

  return sanitizePastProjectsDetailHtml(
    `<div ${PAST_PROJECT_NOTE_CURATION_ATTR}="${PAST_PROJECT_NOTE_CURATION_VALUE}">${projectHtml}</div>`,
  );
};

export const appendPastProjectsNoteInsertHtml = (
  currentHtml: string,
  rows: ProjectGridRow[],
  options: PastProjectNoteInsertOptions = {},
) => {
  const insertHtml = buildPastProjectsNoteInsertHtml(rows, options);
  const sanitizedCurrent = sanitizePastProjectsDetailHtml(currentHtml);
  if (typeof document !== 'undefined') {
    const currentTemplate = document.createElement('template');
    currentTemplate.innerHTML = sanitizedCurrent;
    const existingCuration = currentTemplate.content.querySelector(PAST_PROJECT_NOTE_CURATION_SELECTOR);

    if (existingCuration) {
      if (!insertHtml) {
        existingCuration.remove();
        return sanitizePastProjectsDetailHtml(currentTemplate.innerHTML);
      }
      const insertTemplate = document.createElement('template');
      insertTemplate.innerHTML = insertHtml;
      existingCuration.replaceWith(insertTemplate.content.cloneNode(true));
      return sanitizePastProjectsDetailHtml(currentTemplate.innerHTML);
    }
  }

  if (!insertHtml) {
    return sanitizedCurrent;
  }

  if (!pastProjectsDetailHtmlToPlainText(sanitizedCurrent).trim()) {
    return insertHtml;
  }
  return sanitizePastProjectsDetailHtml(`${sanitizedCurrent}<br><br>${insertHtml}`);
};

/**
 * Regex-only markup-to-text conversion for environments without a DOM (where
 * DOMPurify cannot sanitize). Tag removal repeats until a fixed point so split
 * fragments (e.g. `<<div>br>`) cannot re-form a tag after a single pass.
 */
export const stripPastProjectsDetailMarkup = (html: string) => {
  let text = html.replace(/<br\s*\/?>/gi, '\n').replace(/<\/(div|p)>/gi, '\n');
  let previous: string;
  do {
    previous = text;
    text = text.replace(/<[^>]*>/g, '');
  } while (text !== previous);
  return text;
};

export const pastProjectsDetailHtmlToPlainText = (html: string) => {
  const sanitizedHtml = sanitizePastProjectsDetailHtml(html);

  if (typeof document === 'undefined') {
    return stripPastProjectsDetailMarkup(sanitizedHtml).replace(/\n{3,}/g, '\n\n').trimEnd();
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
