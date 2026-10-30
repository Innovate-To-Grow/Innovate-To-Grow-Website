import {buildLoginPath} from '@/features/auth/api/redirects';
import {pastProjectsDetailHtmlToPlainText, sanitizePastProjectsDetailHtml} from '../../richText/content/pastProjectsDetailText';
import {getExportFileBaseName} from '../../shared/utils/shareHelpers';
import type {ProjectRowsExportContext} from '../../export/support/exportTypes';

// The share-level note is rich text (HTML). Persist the sanitized markup, but collapse an
// effectively-empty note (whitespace / a stray <br>) back to "" so it does not render an empty box.
export const prepareNoteForSave = (html: string) =>
  pastProjectsDetailHtmlToPlainText(html).trim() ? sanitizePastProjectsDetailHtml(html) : '';

export const noteHasContent = (html: string) => pastProjectsDetailHtmlToPlainText(html).trim() !== '';

/**
 * Mirrors the backend's NOTE_MAX_LENGTH (src/apps/projects/serializers/past_project_share.py): the API refuses
 * a longer note, and it counts the note's markup.
 */
export const NOTE_MAX_LENGTH = 50_000;

const formatCount = (count: number) => count.toLocaleString('en-US');

/** Why a note, as prepared for saving, is too long to save; '' when it is not. */
export const noteLengthProblem = (preparedNote: string) =>
  preparedNote.length > NOTE_MAX_LENGTH
    ? `The curation note is too long to save: ${formatCount(preparedNote.length)} characters with its formatting, ` +
      `and the limit is ${formatCount(NOTE_MAX_LENGTH)}. Shorten it before saving.`
    : '';

/** Sign-in link that returns to this page afterwards. */
export const currentLoginPath = () => buildLoginPath(`${window.location.pathname}${window.location.search}`);

export const formatSharedDate = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString('en-US', {month: 'long', day: 'numeric', year: 'numeric'});
};

export interface ExportTarget {
  fileBaseName: string;
  context: ProjectRowsExportContext;
}

/** A shared list exports under its (possibly unsaved, edited) name and note. */
export function sharedListExportTarget(
  title: string,
  edit: {enabled: boolean; titleDraft: string; noteDraft: string; savedNoteHtml: string},
): ExportTarget {
  const sharedTitle = (edit.enabled ? edit.titleDraft : title).trim() || title;
  return {
    fileBaseName: getExportFileBaseName(sharedTitle),
    context: {title: sharedTitle, note: edit.enabled ? prepareNoteForSave(edit.noteDraft) : edit.savedNoteHtml},
  };
}

/**
 * The builder exports with the typed name and note. A blank name exports as the card's title; the
 * shared page's default name is derived by the server from the note when the link is created.
 */
export function builderExportTarget(
  title: string,
  draft: {enabled: boolean; nameDraft: string; noteDraft: string},
): ExportTarget {
  const typedName = draft.enabled ? draft.nameDraft.trim() : '';
  return {
    fileBaseName: getExportFileBaseName(typedName),
    context: {title: typedName || title, note: draft.enabled ? prepareNoteForSave(draft.noteDraft) : ''},
  };
}
