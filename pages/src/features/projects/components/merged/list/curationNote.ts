import {buildLoginPath} from '@/features/auth/api/redirects';
import {draftHandoverHref, isEmbeddedBuilder, PAST_PROJECTS_PATH} from '../../builder/draft/draftHandover';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {pastProjectsDetailHtmlToPlainText, sanitizePastProjectsDetailHtml} from '../../richText/content/pastProjectsDetailText';
import {getExportFileBaseName} from '../../shared/utils/shareHelpers';
import type {ProjectRowsExportContext} from '../../export/support/exportTypes';
import {curationBranding} from './curationBranding';

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

/**
 * Sign-in link that returns to this page afterwards. Never to the widget's chromeless `/_embed/` page: a sign-in
 * opened from the widget comes back to the full builder page at `path` (Past Projects or All Projects).
 */
export const currentLoginPath = (path: string = PAST_PROJECTS_PATH) =>
  buildLoginPath(isEmbeddedBuilder() ? path : `${window.location.pathname}${window.location.search}`);

/** Where "Sign In to Save" leads. */
export interface SignInToSave {
  href: string;
  /** In the widget: the full builder page in a new tab, carrying the draft, where the visitor signs in. */
  inNewTab: boolean;
}

/** `path` is the builder's route, where the widget's draft continues (the page's ProjectCatalog). */
export const signInToSave = (draftRows: readonly ProjectGridRow[], path: string = PAST_PROJECTS_PATH): SignInToSave =>
  isEmbeddedBuilder()
    ? {href: draftHandoverHref(draftRows, path), inNewTab: true}
    : {href: currentLoginPath(path), inNewTab: false};

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

/**
 * A shared list exports under its (possibly unsaved, edited) name and note, its file and heading named after the
 * exported rows (curationBranding).
 */
export function sharedListExportTarget(
  title: string,
  edit: {enabled: boolean; titleDraft: string; noteDraft: string; savedNoteHtml: string},
  rows: readonly ProjectGridRow[],
): ExportTarget {
  const sharedTitle = (edit.enabled ? edit.titleDraft : title).trim() || title;
  const {filePrefix, exportHeading} = curationBranding(rows);
  return {
    fileBaseName: getExportFileBaseName(sharedTitle, filePrefix),
    context: {
      title: sharedTitle,
      note: edit.enabled ? prepareNoteForSave(edit.noteDraft) : edit.savedNoteHtml,
      heading: exportHeading,
    },
  };
}

/**
 * The builder exports with the typed name and note, its file and heading named after the exported rows
 * (curationBranding). A blank name exports as the card's title; the shared page's default name is derived by the
 * server from the note when the link is created.
 */
export function builderExportTarget(
  title: string,
  draft: {enabled: boolean; nameDraft: string; noteDraft: string},
  rows: readonly ProjectGridRow[],
): ExportTarget {
  const typedName = draft.enabled ? draft.nameDraft.trim() : '';
  const {filePrefix, exportHeading} = curationBranding(rows);
  return {
    fileBaseName: getExportFileBaseName(typedName, filePrefix),
    context: {
      title: typedName || title,
      note: draft.enabled ? prepareNoteForSave(draft.noteDraft) : '',
      heading: exportHeading,
    },
  };
}
