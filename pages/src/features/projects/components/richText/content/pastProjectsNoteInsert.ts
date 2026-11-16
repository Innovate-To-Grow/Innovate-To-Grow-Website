import {createProjectGridFingerprint, getProjectRowDetailUrl, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import {
    escapeHtml,
    pastProjectsDetailHtmlToPlainText,
    sanitizePastProjectsDetailHtml,
} from './pastProjectsDetailText';

const PAST_PROJECT_NOTE_CURATION_ATTR = 'data-past-project-note-curation';
const PAST_PROJECT_NOTE_CURATION_VALUE = 'project-summary';
const PAST_PROJECT_NOTE_CURATION_SELECTOR = `div[${PAST_PROJECT_NOTE_CURATION_ATTR}="${PAST_PROJECT_NOTE_CURATION_VALUE}"]`;
// Each inserted project is wrapped in its own div tagged with its dedup fingerprint, so a re-insert
// can read which projects are already in the curation block and skip them.
const PAST_PROJECT_NOTE_ITEM_ATTR = 'data-past-project-key';
const PAST_PROJECT_NOTE_ITEM_SELECTOR = `[${PAST_PROJECT_NOTE_ITEM_ATTR}]`;
const PAST_PROJECT_NOTE_SEPARATOR_HTML = '<div>------------------------------</div>';

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

const fieldLine = (label: string, value: string) =>
  value.trim() ? `<div><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value.trim())}</div>` : '';

// Compact, stable hash (FNV-1a → base36) so the per-project marker stays short instead of embedding
// the whole fingerprint (which would bloat the note and duplicate the abstract text).
const hashString = (value: string) => {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
};

// The dedup identity for an inserted project — id-independent so the same project matches whether
// or not it carries a UUID (mirrors createProjectGridItems' fingerprint-based key).
const projectInsertKey = (row: ProjectGridRow) => hashString(createProjectGridFingerprint(row));

// The field rows for a single project (without the per-project wrapper).
const projectInsertFieldsHtml = (
  row: ProjectGridRow,
  index: number,
  excludedFields: Set<PastProjectNoteInsertField>,
) => {
  // The project's own page: a current-semester project's, or the archive's ('' without an id).
  const href = getProjectRowDetailUrl(row);
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

// A single project wrapped in a keyed div, so re-inserts can detect it. Returns '' when every
// field is excluded (nothing to show).
const projectInsertBlockHtml = (
  row: ProjectGridRow,
  index: number,
  excludedFields: Set<PastProjectNoteInsertField>,
) => {
  const fields = projectInsertFieldsHtml(row, index, excludedFields);
  if (!fields) {
    return '';
  }
  return `<div ${PAST_PROJECT_NOTE_ITEM_ATTR}="${escapeHtml(projectInsertKey(row))}">${fields}</div>`;
};

// Build keyed project blocks joined by separators, numbered starting at `startIndex`.
const buildProjectBlocksHtml = (
  rows: ProjectGridRow[],
  excludedFields: Set<PastProjectNoteInsertField>,
  startIndex: number,
) =>
  rows
    .map((row, offset) => projectInsertBlockHtml(row, startIndex + offset, excludedFields))
    .filter(Boolean)
    .join(PAST_PROJECT_NOTE_SEPARATOR_HTML);

export const buildPastProjectsNoteInsertHtml = (
  rows: ProjectGridRow[],
  options: PastProjectNoteInsertOptions = {},
) => {
  const excludedFields = new Set(options.excludedFields ?? []);
  const projectHtml = buildProjectBlocksHtml(rows, excludedFields, 0);

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
  const excludedFields = new Set(options.excludedFields ?? []);
  const sanitizedCurrent = sanitizePastProjectsDetailHtml(currentHtml);

  if (typeof document !== 'undefined') {
    const currentTemplate = document.createElement('template');
    currentTemplate.innerHTML = sanitizedCurrent;
    const existingCuration = currentTemplate.content.querySelector(PAST_PROJECT_NOTE_CURATION_SELECTOR);

    if (existingCuration) {
      // Append only projects not already present, so any hand edits to existing inserted text
      // survive a re-insert. Numbering continues after the projects already in the block.
      const existingBlocks = existingCuration.querySelectorAll(PAST_PROJECT_NOTE_ITEM_SELECTOR);
      const existingKeys = new Set(
        Array.from(existingBlocks).map((block) => block.getAttribute(PAST_PROJECT_NOTE_ITEM_ATTR) ?? ''),
      );
      const newRows = rows.filter((row) => !existingKeys.has(projectInsertKey(row)));
      const newBlocksHtml = buildProjectBlocksHtml(newRows, excludedFields, existingBlocks.length);

      if (!newBlocksHtml) {
        // Nothing new to add — leave the (possibly edited) note untouched.
        return sanitizedCurrent;
      }

      const prefix = existingBlocks.length ? PAST_PROJECT_NOTE_SEPARATOR_HTML : '';
      const appendTemplate = document.createElement('template');
      appendTemplate.innerHTML = `${prefix}${newBlocksHtml}`;
      existingCuration.appendChild(appendTemplate.content.cloneNode(true));
      return sanitizePastProjectsDetailHtml(currentTemplate.innerHTML);
    }
  }

  const insertHtml = buildPastProjectsNoteInsertHtml(rows, options);
  if (!insertHtml) {
    return sanitizedCurrent;
  }

  if (!pastProjectsDetailHtmlToPlainText(sanitizedCurrent).trim()) {
    return insertHtml;
  }
  return sanitizePastProjectsDetailHtml(`${sanitizedCurrent}<br><br>${insertHtml}`);
};
