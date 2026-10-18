import {useEffect, useId, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {buildLoginPath} from '@/features/auth/api/redirects';
import {DEFAULT_PAST_PROJECT_SHARE_NAME} from '@/features/projects/api';
import {ProjectGridTable} from './ProjectGridTable';
import type {ProjectRowsExporter} from './export/exportTypes';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';
import {RichTextDetailEditor} from './RichTextDetailEditor';
import {RichDetailPreview} from './RichDetailPreview';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {
  PAST_PROJECT_NOTE_INSERT_FIELDS,
  appendPastProjectsNoteInsertHtml,
  pastProjectsDetailHtmlToPlainText,
  sanitizePastProjectsDetailHtml,
  type PastProjectNoteInsertField,
} from './pastProjectsDetailText';
import {SharedEditIcon, SharedSaveIcon} from './shareEditorIcons';
import {getExportFileBaseName, getShareErrorMessage} from './shareHelpers';
import {pluralize} from './saveResults';

interface MergedResultsTableProps {
  id?: string;
  className?: string;
  rows: ProjectGridItem[];
  /** Rows added by the latest save (builder): highlighted, and the table pages to the first of them. */
  recentlyAdded?: {keys: ReadonlySet<string>; token: number} | null;
  /** Saves still loading their projects (builder). Sharing waits, or the link would leave those rows out. */
  pendingSaveCount?: number;
  sharedMode?: boolean;
  title?: string;
  note?: string;
  /** When the shared list was created (ISO 8601), for its meta line. */
  sharedAt?: string;
  editable?: boolean;
  onCreateShare?: (
    rows: ProjectGridRow[],
    name: string,
    note: string,
  ) => Promise<PastProjectShareCreationResult>;
  onUpdateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  onDeleteRow?: (row: ProjectGridItem) => void;
  onDeleteRows?: (rows: ProjectGridItem[]) => void;
  canUndoRows?: boolean;
  onUndoRows?: () => void;
  onResetRows?: () => void;
}

export type PastProjectShareCreationResult =
  | string
  | {
      id: string;
      share_url?: string;
    };

// The share-level note is rich text (HTML). Persist the sanitized markup, but collapse an
// effectively-empty note (whitespace / a stray <br>) back to "" so it does not render an empty box.
const prepareNoteForSave = (html: string) =>
  pastProjectsDetailHtmlToPlainText(html).trim() ? sanitizePastProjectsDetailHtml(html) : '';

type ProjectRowsExportFormat = 'pdf' | 'excel' | 'word';

async function loadProjectRowsExporter(format: ProjectRowsExportFormat): Promise<ProjectRowsExporter> {
  switch (format) {
    case 'pdf':
      return (await import('./export/pdfExport')).exportProjectRowsPdf;
    case 'excel':
      return (await import('./export/excelExport')).exportProjectRowsExcel;
    case 'word':
      return (await import('./export/wordExport')).exportProjectRowsWord;
  }
}

const formatSharedDate = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString('en-US', {month: 'long', day: 'numeric', year: 'numeric'});
};

interface ProjectNoteInsertControlProps {
  rows: ProjectGridRow[];
  excludedFields: Set<PastProjectNoteInsertField>;
  onInsert: () => void;
  onToggleExcludedField: (field: PastProjectNoteInsertField) => void;
}

const ProjectNoteInsertControl = ({
  rows,
  excludedFields,
  onInsert,
  onToggleExcludedField,
}: ProjectNoteInsertControlProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuId = useId();

  return (
    <div
      className={`project-grid-note-insert-control${isOpen ? ' is-open' : ''}`}
      role="group"
      aria-label="Note insert tools"
    >
      <div className="project-grid-note-insert-actions">
        <button type="button" className="itg-btn itg-btn-text" onClick={onInsert} disabled={!rows.length}>
          Insert projects into note
        </button>
        <button
          type="button"
          className="itg-btn itg-btn-text project-grid-note-insert-settings"
          aria-expanded={isOpen}
          aria-controls={isOpen ? menuId : undefined}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setIsOpen((current) => !current)}
        >
          Choose fields
        </button>
      </div>
      {isOpen ? (
        <fieldset id={menuId} className="project-grid-note-insert-menu">
          <legend className="project-grid-note-insert-menu-title">Leave these fields out</legend>
          {PAST_PROJECT_NOTE_INSERT_FIELDS.map((field) => (
            <label key={field.key} className="project-grid-note-insert-option">
              <input
                type="checkbox"
                checked={excludedFields.has(field.key)}
                onChange={() => onToggleExcludedField(field.key)}
              />
              <span>{field.label}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
    </div>
  );
};

export const MergedResultsTable = ({
  id,
  className,
  rows,
  recentlyAdded = null,
  pendingSaveCount = 0,
  sharedMode = false,
  title = 'Saved Merged Results',
  note,
  sharedAt,
  editable = false,
  onCreateShare,
  onUpdateShare,
  onDeleteRow,
  onDeleteRows,
  canUndoRows = false,
  onUndoRows,
  onResetRows,
}: MergedResultsTableProps) => {
  const {isAuthenticated} = useAuth();
  const canShare = !sharedMode && Boolean(onCreateShare) && isAuthenticated;
  const canEditShared = sharedMode && editable && Boolean(onUpdateShare);
  // Checkbox-based bulk removal of merged rows (builder only — shared-mode edits go through the API
  // per row). Drives the "check rows → Remove Selected" flow.
  const canBulkRemove = !sharedMode && Boolean(onDeleteRows);

  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    expandAllByDefault: sharedMode,
  });
  const [statusMessage, setStatusMessage] = useState('');
  const [isSharing, setIsSharing] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [editTitleDraft, setEditTitleDraft] = useState(title);
  const [editNoteDraft, setEditNoteDraft] = useState(note ?? '');
  const [isSavingShareEdit, setIsSavingShareEdit] = useState(false);
  const [sharedRowsUndo, setSharedRowsUndo] = useState<ProjectGridRow[] | null>(null);
  const [pendingBulkAction, setPendingBulkAction] = useState<'reset-builder' | 'remove-all-shared' | null>(null);
  const [isEditingSharedTitle, setIsEditingSharedTitle] = useState(false);
  const [isEditingSharedNote, setIsEditingSharedNote] = useState(false);
  const [excludedProjectNoteInsertFields, setExcludedProjectNoteInsertFields] = useState<
    Set<PastProjectNoteInsertField>
  >(() => new Set());
  // Track the last note/title props we synced drafts from, so a prop change resets the draft and
  // closes the inline editor — done during render (React's documented "adjusting state on prop
  // change" pattern) rather than in an effect, avoiding the extra commit a synchronous setState in
  // an effect would cause.
  const [lastSyncedNote, setLastSyncedNote] = useState(note ?? '');
  const [lastSyncedTitle, setLastSyncedTitle] = useState(title);
  const [revealedToken, setRevealedToken] = useState(recentlyAdded?.token ?? null);
  const editTitleInputRef = useRef<HTMLInputElement>(null);
  const shareUrlInputRef = useRef<HTMLInputElement>(null);
  const isMountedRef = useRef(true);
  const headingId = useId();
  const shareUrlInputId = useId();
  const nameInputId = useId();
  const nameHintId = useId();
  const phoneListId = useId();
  // Phones show the saved list collapsed behind a disclosure (wider screens always show it, see projects.css).
  const [isPhoneListOpen, setIsPhoneListOpen] = useState(false);

  // The shareable URL is just the current page URL in shared mode — derive it from the prop instead
  // of mirroring window.location.href into state via an effect.
  const shareUrl = sharedMode ? window.location.href : '';

  if (lastSyncedNote !== (note ?? '')) {
    setLastSyncedNote(note ?? '');
    setEditNoteDraft(note ?? '');
    setIsEditingSharedNote(false);
  }

  if (lastSyncedTitle !== title) {
    setLastSyncedTitle(title);
    setEditTitleDraft(title);
    setIsEditingSharedTitle(false);
  }

  // After a save, move to the page holding the first newly added row (the table sorts by semester, so
  // older projects otherwise land on a later page and the save looks like it did nothing).
  if (recentlyAdded && recentlyAdded.token !== revealedToken) {
    setRevealedToken(recentlyAdded.token);
    const firstAddedIndex = table.sortedRows.findIndex((row) => recentlyAdded.keys.has(row.__key));
    if (firstAddedIndex >= 0) {
      table.setPage(Math.floor(firstAddedIndex / table.pageSize));
    }
  }
  const shownKeys = new Set(table.filteredRows.map((row) => row.__key));
  const hiddenAddedCount = recentlyAdded
    ? rows.filter((row) => recentlyAdded.keys.has(row.__key) && !shownKeys.has(row.__key)).length
    : 0;

  useEffect(() => {
    // Set in the body too: StrictMode runs this cleanup once on mount, which would leave it false.
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (isEditingSharedTitle) {
      editTitleInputRef.current?.focus();
      editTitleInputRef.current?.select();
    }
  }, [isEditingSharedTitle]);

  // The full saved snapshot — used by title/note/delete saves and by the shared-mode export.
  const allRows = useMemo(() => rows.map(stripProjectGridItem), [rows]);
  // The visible (filtered/sorted) rows — used for builder share-create and builder export.
  const visibleRows = useMemo(() => table.sortedRows.map(stripProjectGridItem), [table.sortedRows]);

  const sharedNoteHtml = sharedMode ? (note ?? '') : '';
  const sharedNoteHasContent = pastProjectsDetailHtmlToPlainText(sharedNoteHtml).trim() !== '';
  // In shared mode the export represents the whole shared snapshot, so a viewer's transient table
  // search must not narrow it. In builder mode the visible (filtered) rows ARE the selection.
  const exportRows = sharedMode ? allRows : visibleRows;
  // Built on click rather than every render: prepareNoteForSave sanitizes and walks the whole note.
  const buildExportTarget = () => {
    if (sharedMode) {
      const sharedTitle = (canEditShared ? editTitleDraft : title).trim() || title;
      return {
        fileBaseName: getExportFileBaseName(sharedTitle),
        context: {title: sharedTitle, note: canEditShared ? prepareNoteForSave(editNoteDraft) : sharedNoteHtml},
      };
    }
    // In the builder, export with the typed name and note. A blank name exports as this card's title; the
    // shared page's default name is derived by the server from the note when the link is created.
    const typedName = canShare ? nameDraft.trim() : '';
    return {
      fileBaseName: getExportFileBaseName(typedName),
      context: {title: typedName || title, note: canShare ? prepareNoteForSave(noteDraft) : ''},
    };
  };
  const excludedProjectNoteInsertFieldList = useMemo(
    () => Array.from(excludedProjectNoteInsertFields),
    [excludedProjectNoteInsertFields],
  );

  const handleExport = async (format: ProjectRowsExportFormat, label: string) => {
    try {
      const exporter = await loadProjectRowsExporter(format);
      const {fileBaseName, context} = buildExportTarget();
      await exporter(exportRows, fileBaseName, context);
    } catch {
      // Dynamic-import (code-split chunk) or serialization failures otherwise reject silently.
      setStatusMessage(`Unable to export ${label}. Please try again.`);
    }
  };
  const hasTitleChanges = editTitleDraft.trim() !== title.trim();
  // Compare both sides through the same client sanitizer so a no-op edit (the editor re-emits
  // normalized markup) is not treated as a change versus the server-stored note.
  // Compare both sides through prepareNoteForSave — the exact normalization used for the write —
  // so emptying a note to residual markup ('<br>', '<div></div>') is not mistaken for a change and
  // does not fire a no-op save with a misleading "Note updated." status.
  const hasNoteChanges = prepareNoteForSave(editNoteDraft) !== prepareNoteForSave(note ?? '');

  const handleCreateShare = async () => {
    const trimmedName = nameDraft.trim();
    // name is optional — when blank the backend derives one from the curation content. Only rows are
    // required.
    if (!onCreateShare || !visibleRows.length || pendingSaveCount > 0) {
      return;
    }

    // Mirror the backend cap (serializer rejects >1000 rows) with a specific message instead
    // of letting the request fail with the generic error below.
    if (visibleRows.length > 1000) {
      setStatusMessage('A shared page can include at most 1000 projects. Remove some rows and try again.');
      return;
    }

    setIsSharing(true);
    setStatusMessage('');
    try {
      await onCreateShare(visibleRows, trimmedName, prepareNoteForSave(noteDraft));
      if (isMountedRef.current) {
        setStatusMessage('Opening shareable link...');
      }
    } catch (error) {
      if (isMountedRef.current) {
        setStatusMessage(getShareErrorMessage(error));
      }
    } finally {
      if (isMountedRef.current) {
        setIsSharing(false);
      }
    }
  };

  const handleInsertVisibleProjectsIntoNote = () => {
    setNoteDraft((current) =>
      appendPastProjectsNoteInsertHtml(current, visibleRows, {excludedFields: excludedProjectNoteInsertFieldList}),
    );
  };

  const handleInsertSharedProjectsIntoNote = () => {
    setEditNoteDraft((current) =>
      appendPastProjectsNoteInsertHtml(current, allRows, {excludedFields: excludedProjectNoteInsertFieldList}),
    );
  };

  const handleToggleProjectNoteInsertField = (field: PastProjectNoteInsertField) => {
    setExcludedProjectNoteInsertFields((current) => {
      const next = new Set(current);
      if (next.has(field)) {
        next.delete(field);
      } else {
        next.add(field);
      }
      return next;
    });
  };

  const handleCopyShareUrl = async (input: HTMLInputElement) => {
    if (!shareUrl) {
      return;
    }

    input.select();

    try {
      if (window.navigator.clipboard?.writeText) {
        await window.navigator.clipboard.writeText(shareUrl);
        setStatusMessage('Shareable URL copied.');
        return;
      }
    } catch {
      // Fall through to the selected-input copy fallback below.
    }

    try {
      if (document.execCommand('copy')) {
        setStatusMessage('Shareable URL copied.');
        return;
      }
    } catch {
      // Keep the final fallback message below.
    }

    setStatusMessage('Unable to copy URL. Select the link and copy it manually.');
  };

  const handleUpdateSharedPage = async (
    nextRows: ProjectGridRow[],
    nextName: string,
    nextNote: string,
    successMessage: string,
  ) => {
    if (!onUpdateShare) {
      return false;
    }

    setIsSavingShareEdit(true);
    setStatusMessage('');
    try {
      await onUpdateShare(nextRows, nextName, nextNote);
      setStatusMessage(successMessage);
      return true;
    } catch {
      setStatusMessage('Unable to update this shared page. Please try again.');
      return false;
    } finally {
      setIsSavingShareEdit(false);
    }
  };

  const handleSharedTitleAction = async () => {
    if (!isEditingSharedTitle) {
      setIsEditingSharedTitle(true);
      setIsEditingSharedNote(false);
      return;
    }

    const trimmedTitle = editTitleDraft.trim();
    if (!hasTitleChanges) {
      setIsEditingSharedTitle(false);
      return;
    }

    const saved = await handleUpdateSharedPage(allRows, trimmedTitle, note ?? '', 'Name updated.');
    if (saved) {
      setIsEditingSharedTitle(false);
    }
  };

  const handleSharedNoteAction = async () => {
    if (!isEditingSharedNote) {
      setIsEditingSharedNote(true);
      setIsEditingSharedTitle(false);
      return;
    }

    if (!hasNoteChanges) {
      setIsEditingSharedNote(false);
      return;
    }

    const saved = await handleUpdateSharedPage(allRows, title, prepareNoteForSave(editNoteDraft), 'Note updated.');
    if (saved) {
      setIsEditingSharedNote(false);
    }
  };

  const handleDeleteSharedRow = async (row: ProjectGridItem) => {
    const rowIndex = rows.findIndex((candidate) => candidate.__key === row.__key);
    if (rowIndex < 0) {
      return;
    }
    const nextRows = allRows.filter((_, index) => index !== rowIndex);
    if (!nextRows.length) {
      setStatusMessage('A shared page needs at least one project.');
      return;
    }
    const saved = await handleUpdateSharedPage(nextRows, title, note ?? '', 'Project removed.');
    if (saved) {
      setSharedRowsUndo(allRows);
    }
  };

  // While a link is being created the rows stay as they were at the click: the link is made from them.
  const handleDeleteMergedRow = async (row: ProjectGridItem) => {
    if (!onDeleteRow || isSharing) {
      return;
    }

    onDeleteRow(row);
  };

  const handleRemoveSelectedMergedRows = () => {
    if (!onDeleteRows || !table.hasSelection || isSharing) {
      return;
    }
    onDeleteRows(table.selectedRows);
    table.clearSelection();
  };

  const handleUndoSharedRows = async () => {
    if (!sharedRowsUndo) {
      return;
    }

    const saved = await handleUpdateSharedPage(sharedRowsUndo, title, note ?? '', 'Change undone.');
    if (saved) {
      setSharedRowsUndo(null);
    }
  };

  const handleConfirmBulkAction = () => {
    if (pendingBulkAction === 'reset-builder' && !isSharing) {
      onResetRows?.();
    }

    if (pendingBulkAction === 'remove-all-shared') {
      setStatusMessage(
        'A shared page needs at least one project. Remove rows individually, or delete the shared page if it is no longer needed.',
      );
    }

    setPendingBulkAction(null);
  };

  const exportGroup = (
    <div className="project-grid-toolbar-cluster project-grid-export-group" role="group" aria-label="Export">
      <span className="project-grid-group-label" aria-hidden="true">
        Export
      </span>
      <button
        type="button"
        className="itg-btn itg-btn-outline"
        onClick={() => void handleExport('pdf', 'PDF')}
        disabled={!exportRows.length}
      >
        PDF
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-outline"
        onClick={() => void handleExport('excel', 'Excel')}
        disabled={!exportRows.length}
      >
        Excel
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-outline"
        onClick={() => void handleExport('word', 'Microsoft Word')}
        disabled={!exportRows.length}
      >
        <span>
          <span className="project-grid-wide-only">Microsoft</span> Word
        </span>
      </button>
    </div>
  );

  // Shared page: the link to pass on, with a Copy button and the exports beside it.
  const shareResultPanel = shareUrl ? (
    <div className="itg-panel project-grid-share-result">
      <div className="itg-field project-grid-share-result-field">
        <label className="project-grid-field-label" htmlFor={shareUrlInputId}>
          Shareable link
        </label>
        <div className="project-grid-share-result-row">
          <input
            ref={shareUrlInputRef}
            id={shareUrlInputId}
            type="text"
            className="itg-input project-grid-share-result-input"
            value={shareUrl}
            readOnly
            title="Click to copy the link"
            onFocus={(event) => {
              void handleCopyShareUrl(event.currentTarget);
            }}
            onClick={(event) => {
              void handleCopyShareUrl(event.currentTarget);
            }}
          />
          <button
            type="button"
            className="itg-btn itg-btn-primary project-grid-share-copy"
            onClick={() => {
              if (shareUrlInputRef.current) void handleCopyShareUrl(shareUrlInputRef.current);
            }}
          >
            Copy link
          </button>
        </div>
      </div>
      {exportGroup}
    </div>
  ) : null;

  const createShareButton = canShare ? (
    <button
      type="button"
      className="itg-btn itg-btn-primary"
      onClick={() => void handleCreateShare()}
      disabled={!visibleRows.length || isSharing || pendingSaveCount > 0}
    >
      {isSharing ? 'Creating URL...' : 'Get Shareable URL'}
    </button>
  ) : null;
  // Shown beside the button rather than on a line of its own.
  const pendingSaveHint =
    canShare && pendingSaveCount > 0 ? (
      <p className="project-grid-share-pending" role="status">
        Waiting for projects to finish saving…
      </p>
    ) : null;
  // In the builder the link and exports take the rows the search shows; say so when it hides some, above
  // all when it hides projects that were just saved.
  const shownCount = table.filteredRows.length;
  const narrowedHint =
    !sharedMode && shownCount < rows.length ? (
      <p className="itg-notice project-grid-narrowed-hint" role={hiddenAddedCount ? 'status' : undefined}>
        {hiddenAddedCount
          ? `${hiddenAddedCount === 1 ? '1 newly saved project is' : `${hiddenAddedCount} newly saved projects are`} hidden by your search.`
          : `Your search shows ${shownCount} of ${rows.length} saved projects.`}{' '}
        The shareable link and exports include only the {shownCount} it shows.{' '}
        <button type="button" className="itg-btn itg-btn-text past-projects-status-action" onClick={() => table.setSearch('')}>
          Clear search
        </button>
      </p>
    ) : null;

  const sharedNoteAction = (
    <button
      type="button"
      className={`itg-btn itg-btn-text project-grid-share-editor-icon-button project-grid-share-note-action${
        isEditingSharedNote ? ' is-active' : ''
      }`}
      onClick={() => void handleSharedNoteAction()}
      disabled={isSavingShareEdit}
    >
      {isEditingSharedNote ? <SharedSaveIcon /> : <SharedEditIcon />}
      {isEditingSharedNote ? 'Save curation note' : 'Edit curation note'}
    </button>
  );

  const sharedEditor = canEditShared ? (
    <div className={`project-grid-share-editor${isEditingSharedNote ? ' is-editing' : ''}`}>
      <RichTextDetailEditor
        id="past-project-shared-note-editor"
        label="Curation note"
        value={editNoteDraft}
        placeholder="Add a curation note (shown at the top of the shared page)."
        readOnly={!isEditingSharedNote}
        autoFocus={isEditingSharedNote}
        headerAction={sharedNoteAction}
        onChange={setEditNoteDraft}
      />
      {isEditingSharedNote ? (
        <ProjectNoteInsertControl
          rows={allRows}
          excludedFields={excludedProjectNoteInsertFields}
          onInsert={handleInsertSharedProjectsIntoNote}
          onToggleExcludedField={handleToggleProjectNoteInsertField}
        />
      ) : null}
    </div>
  ) : null;

  const recoveryButtons =
    onUndoRows || onResetRows || canEditShared || canBulkRemove ? (
      <div className="project-grid-toolbar-cluster project-grid-edit-group" role="group" aria-label="Edit list">
        {canBulkRemove ? (
          <button
            type="button"
            className="itg-btn itg-btn-text"
            onClick={handleRemoveSelectedMergedRows}
            disabled={!table.hasSelection || isSharing}
          >
            Remove Selected
          </button>
        ) : null}
        {onUndoRows ? (
          <button
            type="button"
            className="itg-btn itg-btn-text"
            onClick={onUndoRows}
            disabled={!canUndoRows || isSharing}
          >
            Undo Merged Change
          </button>
        ) : null}
        {!sharedMode && onResetRows ? (
          <button
            type="button"
            className="itg-btn itg-btn-text itg-btn-danger"
            onClick={() => setPendingBulkAction('reset-builder')}
            disabled={!rows.length || isSharing}
          >
            Reset Merged Results
          </button>
        ) : null}
        {canEditShared ? (
          <>
            <button
              type="button"
              className="itg-btn itg-btn-text"
              onClick={() => void handleUndoSharedRows()}
              disabled={!sharedRowsUndo || isSavingShareEdit}
            >
              Undo Shared Change
            </button>
            <button
              type="button"
              className="itg-btn itg-btn-text itg-btn-danger"
              onClick={() => setPendingBulkAction('remove-all-shared')}
              disabled={isSavingShareEdit}
            >
              Remove All
            </button>
          </>
        ) : null}
      </div>
    ) : null;

  const sharedDate = formatSharedDate(sharedAt);
  const titleEditButton = canEditShared ? (
    <button
      type="button"
      className={`itg-btn itg-btn-text project-grid-share-editor-icon-button project-grid-share-title-action${
        isEditingSharedTitle ? ' is-active' : ''
      }`}
      onClick={() => void handleSharedTitleAction()}
      disabled={isSavingShareEdit}
    >
      {isEditingSharedTitle ? <SharedSaveIcon /> : <SharedEditIcon />}
      {isEditingSharedTitle ? 'Save name' : 'Edit name'}
    </button>
  ) : null;

  const header = sharedMode ? (
    <header className="project-grid-shared-header">
      <p className="itg-eyebrow">Shared list · Past Projects</p>
      <div className={`project-grid-share-title-editor${isEditingSharedTitle ? ' is-editing' : ''}`}>
        {canEditShared && isEditingSharedTitle ? (
          <input
            ref={editTitleInputRef}
            type="text"
            className="itg-input project-grid-share-title-input"
            aria-label="Shared page name"
            value={editTitleDraft}
            maxLength={200}
            onChange={(event) => setEditTitleDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void handleSharedTitleAction();
              }
            }}
          />
        ) : (
          <h1 id={headingId} className="itg-page-title project-grid-card-title" tabIndex={-1}>
            {title}
          </h1>
        )}
        {titleEditButton}
      </div>
      <p className="itg-page-meta">
        {pluralize(rows.length, 'project')}
        {sharedDate ? ` · shared ${sharedDate}` : ''}
      </p>
    </header>
  ) : (
    <div className="project-grid-card-header">
      <h2 id={headingId} className="project-grid-card-title" tabIndex={-1}>
        {title}
      </h2>
      <p className="project-grid-card-count">
        <strong>{pluralize(rows.length, 'project')}</strong> in this list
      </p>
    </div>
  );

  const shareSection =
    !sharedMode && onCreateShare ? (
      <div className="project-grid-share">
        <h3 className="project-grid-share-title">Share this list</h3>
        {isAuthenticated ? (
          <>
            <div className="project-grid-share-fields">
              <div className="itg-field project-grid-share-note">
                <label className="project-grid-share-note-label" htmlFor={nameInputId}>
                  Shared page name <span className="project-grid-label-hint">(optional)</span>
                </label>
                <input
                  id={nameInputId}
                  type="text"
                  className="itg-input project-grid-share-name-input"
                  value={nameDraft}
                  maxLength={200}
                  placeholder={DEFAULT_PAST_PROJECT_SHARE_NAME}
                  aria-describedby={nameHintId}
                  onChange={(event) => setNameDraft(event.target.value)}
                />
                <p id={nameHintId} className="project-grid-share-name-hint">
                  Leave it blank to use the first line of your note.
                </p>
              </div>
              <div className="project-grid-share-note">
                <RichTextDetailEditor
                  id="past-project-share-note"
                  label="Curation note"
                  labelHint="(shown at the top of the shared page)"
                  value={noteDraft}
                  placeholder="Optional — add context for whoever opens the shareable link."
                  onChange={setNoteDraft}
                />
                <ProjectNoteInsertControl
                  rows={visibleRows}
                  excludedFields={excludedProjectNoteInsertFields}
                  onInsert={handleInsertVisibleProjectsIntoNote}
                  onToggleExcludedField={handleToggleProjectNoteInsertField}
                />
              </div>
            </div>
            <div className="project-grid-share-actions">
              {createShareButton}
              {pendingSaveHint ?? (
                <span className="project-grid-share-actions-note">Anyone with the link can view this list.</span>
              )}
            </div>
          </>
        ) : (
          <p className="project-grid-share-login-hint">
            <a href={buildLoginPath(`${window.location.pathname}${window.location.search}`)}>Sign in</a> to name this list
            and get a shareable link.
          </p>
        )}
      </div>
    ) : null;

  return (
    <section
      id={id}
      className={`${sharedMode ? 'project-grid-shared-list' : 'itg-panel project-grid-card project-grid-merged'}${
        className ? ` ${className}` : ''
      }`}
      aria-labelledby={sharedMode && isEditingSharedTitle ? undefined : headingId}
      aria-label={sharedMode && isEditingSharedTitle ? 'Shared list' : undefined}
    >
      {header}

      {sharedMode ? shareResultPanel : null}

      {sharedEditor}

      {!sharedEditor && sharedNoteHasContent ? (
        <div className="project-grid-shared-note">
          <p className="project-grid-shared-note-label">Curation note</p>
          <RichDetailPreview className="project-grid-shared-detail-text itg-content" html={sharedNoteHtml} />
        </div>
      ) : null}

      {narrowedHint}

      {sharedMode ? null : (
        <button
          type="button"
          className="itg-btn itg-btn-text project-grid-phone-list-toggle"
          aria-expanded={isPhoneListOpen}
          aria-controls={phoneListId}
          onClick={() => setIsPhoneListOpen((current) => !current)}
        >
          {isPhoneListOpen ? 'Hide the saved projects' : `Show the ${pluralize(rows.length, 'saved project')}`}
          <span aria-hidden="true">{isPhoneListOpen ? ' ▴' : ' ▾'}</span>
        </button>
      )}

      <div id={phoneListId} className={`project-grid-phone-list${isPhoneListOpen ? ' is-open' : ''}`}>
        <ProjectGridTable
          // Rows saved before the shared-add path hydrated them carry an id but no abstract
          // or student names. Fetch those on expand so Details is not a dead end on an existing
          // shared page; rows that already carry their own content never request anything.
          loadMissingDetails
          linkScope="past"
          columns={PAST_PROJECT_GRID_COLUMNS}
          rows={rows}
          highlightedKeys={recentlyAdded?.keys}
          pagedRows={table.pagedRows}
          filteredCount={table.filteredRows.length}
          totalCount={rows.length}
          search={table.search}
          searchLabel="Search this list"
          searchPlaceholder="Team, project, organization…"
          // Under the shared list's h1, or inside the saved-results card titled with an h2.
          noResultsHeadingLevel={sharedMode ? 2 : 3}
          sortField={table.sortField}
          sortDirection={table.sortDirection}
          onSearchChange={table.setSearch}
          onSortChange={table.toggleSort}
          expandedKeys={table.expandedKeys}
          onToggleExpanded={table.toggleExpanded}
          onToggleAllDetails={table.toggleAllDetails}
          allDetailsExpanded={table.allDetailsExpanded}
          page={table.page}
          totalPages={table.totalPages}
          onPageChange={table.setPage}
          pageSize={table.pageSize}
          pageSizeOptions={table.pageSizeOptions}
          onPageSizeChange={table.setPageSize}
          emptyMessage={sharedMode ? 'This shared list has no projects.' : 'No merged results saved yet.'}
          countLabel="projects"
          onDeleteRow={sharedMode ? (canEditShared ? handleDeleteSharedRow : undefined) : handleDeleteMergedRow}
          deleteDisabled={!sharedMode && isSharing}
          selectable={canBulkRemove}
          selectedKeys={table.selectedKeys}
          selectAllStateRows={table.filteredRows}
          onToggleSelected={table.toggleSelected}
          onToggleSelectAll={() => {
            // Select-all targets the rows currently visible (matching the active search), so a
            // narrowed view + Remove Selected can never delete rows the user cannot see.
            const visible = table.filteredRows;
            const allVisibleSelected =
              visible.length > 0 && visible.every((row) => table.selectedKeys.has(row.__key));
            if (allVisibleSelected) {
              table.clearSelection();
            } else {
              table.selectRows(visible);
            }
          }}
          toolbarPlacement="bottom"
          toolbar={
            sharedMode ? (
              recoveryButtons
            ) : (
              <div className="project-grid-inline-actions">
                {exportGroup}
                {recoveryButtons}
              </div>
            )
          }
        />
      </div>

      {shareSection}

      {pendingBulkAction ? (
        <PastProjectsDialog
          title={pendingBulkAction === 'reset-builder' ? 'Reset merged results?' : 'Remove all projects?'}
          confirmLabel={pendingBulkAction === 'reset-builder' ? 'Reset Merged Results' : 'Close'}
          showCancel={pendingBulkAction === 'reset-builder'}
          onCancel={() => setPendingBulkAction(null)}
          onConfirm={handleConfirmBulkAction}
        >
          {pendingBulkAction === 'reset-builder' ? (
            <p>Clear every project from the saved merged results? You can undo this immediately afterward.</p>
          ) : (
            <p>
              This shared page cannot be saved with zero projects because the API requires at least one row. Remove
              rows individually, or delete the shared page if it is no longer needed.
            </p>
          )}
        </PastProjectsDialog>
      ) : null}

      {statusMessage ? (
        <p className="project-grid-status" role="status">
          {statusMessage}
        </p>
      ) : null}
    </section>
  );
};
