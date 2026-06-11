import {useEffect, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {buildLoginPath} from '@/features/auth/api/redirects';
import {ProjectGridTable} from './ProjectGridTable';
import {
  exportProjectRowsExcel,
  exportProjectRowsPdf,
  exportProjectRowsWord,
  type ProjectRowsExporter,
} from './export';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';
import {RichTextDetailEditor} from './RichTextDetailEditor';
import {RichDetailPreview} from './RichDetailPreview';
import {
  PAST_PROJECT_NOTE_INSERT_FIELDS,
  appendPastProjectsNoteInsertHtml,
  pastProjectsDetailHtmlToPlainText,
  sanitizePastProjectsDetailHtml,
  type PastProjectNoteInsertField,
} from './pastProjectsDetailText';
import {InsertProjectsIcon, InsertProjectsSettingsIcon, SharedEditIcon, SharedSaveIcon} from './shareEditorIcons';
import {getExportFileBaseName, getShareErrorMessage} from './shareHelpers';

interface MergedResultsTableProps {
  rows: ProjectGridItem[];
  sharedMode?: boolean;
  title?: string;
  note?: string;
  editable?: boolean;
  onCreateShare?: (
    rows: ProjectGridRow[],
    name: string,
    note: string,
  ) => Promise<PastProjectShareCreationResult>;
  onUpdateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  onDeleteRow?: (row: ProjectGridItem) => void;
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

  return (
    <div
      className={`project-grid-note-insert-control${isOpen ? ' is-open' : ''}`}
      role="group"
      aria-label="Note insert tools"
    >
      <div className="project-grid-note-insert-actions">
        <button
          type="button"
          className="project-grid-rich-editor-button project-grid-rich-editor-button--insert-projects"
          aria-label="Insert projects into note"
          title="Insert projects into note"
          onClick={onInsert}
          disabled={!rows.length}
        >
          <InsertProjectsIcon />
        </button>
        <button
          type="button"
          className="project-grid-rich-editor-button project-grid-rich-editor-button--insert-settings"
          aria-label="Project insert settings"
          title="Project insert settings"
          aria-expanded={isOpen}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setIsOpen((current) => !current)}
        >
          <InsertProjectsSettingsIcon />
        </button>
      </div>
      {isOpen ? (
        <div className="project-grid-note-insert-menu" role="group" aria-label="Exclude inserted fields">
          <p className="project-grid-note-insert-menu-title">Exclude</p>
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
        </div>
      ) : null}
    </div>
  );
};

export const MergedResultsTable = ({
  rows,
  sharedMode = false,
  title = 'Saved Merged Results',
  note,
  editable = false,
  onCreateShare,
  onUpdateShare,
  onDeleteRow,
}: MergedResultsTableProps) => {
  const {isAuthenticated} = useAuth();
  const canShare = !sharedMode && Boolean(onCreateShare) && isAuthenticated;
  const canEditShared = sharedMode && editable && Boolean(onUpdateShare);

  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    expandAllByDefault: sharedMode,
  });
  const [shareUrl, setShareUrl] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isSharing, setIsSharing] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [editTitleDraft, setEditTitleDraft] = useState(title);
  const [editNoteDraft, setEditNoteDraft] = useState(note ?? '');
  const [isSavingShareEdit, setIsSavingShareEdit] = useState(false);
  const [isEditingSharedTitle, setIsEditingSharedTitle] = useState(false);
  const [isEditingSharedNote, setIsEditingSharedNote] = useState(false);
  const [excludedProjectNoteInsertFields, setExcludedProjectNoteInsertFields] = useState<
    Set<PastProjectNoteInsertField>
  >(() => new Set());
  const editTitleInputRef = useRef<HTMLInputElement>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (sharedMode) {
      setShareUrl(window.location.href);
    }
  }, [sharedMode]);

  useEffect(() => {
    setEditNoteDraft(note ?? '');
    setIsEditingSharedNote(false);
  }, [note]);

  useEffect(() => {
    setEditTitleDraft(title);
    setIsEditingSharedTitle(false);
  }, [title]);

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
  const sharedExportTitle = (canEditShared ? editTitleDraft : title).trim() || title;
  const sharedExportNote = canEditShared ? prepareNoteForSave(editNoteDraft) : sharedNoteHtml;
  const sharedExportFileBaseName = getExportFileBaseName(sharedExportTitle);
  const exportTitle = sharedMode ? sharedExportTitle : title;
  const exportNote = sharedMode ? sharedExportNote : '';
  const exportFileBaseName = sharedMode ? sharedExportFileBaseName : 'past-projects';
  // In shared mode the export represents the whole shared snapshot, so a viewer's transient table
  // search must not narrow it. In builder mode the visible (filtered) rows ARE the selection.
  const exportRows = sharedMode ? allRows : visibleRows;
  const exportContext = {
    note: exportNote,
    title: exportTitle,
  };
  const excludedProjectNoteInsertFieldList = useMemo(
    () => Array.from(excludedProjectNoteInsertFields),
    [excludedProjectNoteInsertFields],
  );

  const handleExport = async (exporter: ProjectRowsExporter, label: string) => {
    try {
      await exporter(exportRows, exportFileBaseName, exportContext);
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
    if (!onCreateShare || !visibleRows.length || !trimmedName) {
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
        return;
      }
    } catch {
      // Fall through to the selected-input copy fallback below.
    }

    try {
      if (document.execCommand('copy')) {
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
    if (!trimmedTitle) {
      setStatusMessage('Name is required.');
      return;
    }

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
    await handleUpdateSharedPage(nextRows, title, note ?? '', 'Project removed.');
  };

  const handleDeleteMergedRow = async (row: ProjectGridItem) => {
    if (!onDeleteRow) {
      return;
    }

    onDeleteRow(row);
  };

  const shareResultPanel = shareUrl ? (
    <div className="project-grid-share-result" role="status">
      <div className="project-grid-share-result-copy">
        <p className="project-grid-share-result-label">Shareable link</p>
      </div>
      <div className="project-grid-share-result-row">
        <input
          type="text"
          className="project-grid-share-result-input"
          aria-label="Shareable URL"
          value={shareUrl}
          readOnly
          title="Click to copy URL"
          onFocus={(event) => {
            void handleCopyShareUrl(event.currentTarget);
          }}
          onClick={(event) => {
            void handleCopyShareUrl(event.currentTarget);
          }}
        />
      </div>
    </div>
  ) : null;

  const sharedNoteAction = (
    <button
      type="button"
      className={`project-grid-share-editor-icon-button project-grid-share-note-action${
        isEditingSharedNote ? ' is-active' : ''
      }`}
      aria-label={isEditingSharedNote ? 'Save Note' : 'Edit Note'}
      title={isEditingSharedNote ? 'Save Note' : 'Edit Note'}
      onClick={() => void handleSharedNoteAction()}
      disabled={isSavingShareEdit}
    >
      {isEditingSharedNote ? <SharedSaveIcon /> : <SharedEditIcon />}
    </button>
  );

  const sharedNoteHeaderAction = (
    <>
      {isEditingSharedNote ? (
        <ProjectNoteInsertControl
          rows={allRows}
          excludedFields={excludedProjectNoteInsertFields}
          onInsert={handleInsertSharedProjectsIntoNote}
          onToggleExcludedField={handleToggleProjectNoteInsertField}
        />
      ) : null}
      {sharedNoteAction}
    </>
  );

  const sharedEditor = canEditShared ? (
    <div className={`project-grid-share-editor${isEditingSharedNote ? ' is-editing' : ''}`}>
      <RichTextDetailEditor
        id="past-project-shared-note-editor"
        label="Note"
        value={editNoteDraft}
        placeholder="Add a note (shown at the top of the shared page)."
        readOnly={!isEditingSharedNote}
        autoFocus={isEditingSharedNote}
        headerAction={sharedNoteHeaderAction}
        onChange={setEditNoteDraft}
      />
    </div>
  ) : null;

  return (
    <section className="project-grid-card">
      <div className={`project-grid-card-header${canEditShared ? ' project-grid-share-card-header' : ''}`}>
        <div className="project-grid-share-title-content">
          {canEditShared ? (
            <div className={`project-grid-share-title-editor${isEditingSharedTitle ? ' is-editing' : ''}`}>
              {isEditingSharedTitle ? (
                <input
                  ref={editTitleInputRef}
                  type="text"
                  className="project-grid-share-title-input"
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
                <h2 className="project-grid-card-title">{title}</h2>
              )}
            </div>
          ) : (
            <h2 className="project-grid-card-title">{title}</h2>
          )}
          <p className="project-grid-card-copy">
            {sharedMode
              ? 'Browse the saved merged results from this shared link.'
              : 'Merge filtered search tables into one saved result set, then export or share it.'}
          </p>
        </div>
        {canEditShared ? (
          <button
            type="button"
            className={`project-grid-share-editor-icon-button project-grid-share-title-action${
              isEditingSharedTitle ? ' is-active' : ''
            }`}
            aria-label={isEditingSharedTitle ? 'Save Name' : 'Edit Name'}
            title={isEditingSharedTitle ? 'Save Name' : 'Edit Name'}
            onClick={() => void handleSharedTitleAction()}
            disabled={isSavingShareEdit}
          >
            {isEditingSharedTitle ? <SharedSaveIcon /> : <SharedEditIcon />}
          </button>
        ) : null}
      </div>

      {sharedMode ? shareResultPanel : null}

      {sharedEditor}

      {!sharedEditor && sharedNoteHasContent ? (
        <div className="project-grid-shared-note">
          <p className="project-grid-shared-note-label">Note</p>
          <RichDetailPreview className="project-grid-shared-detail-text" html={sharedNoteHtml} />
        </div>
      ) : null}

      {!sharedMode && onCreateShare ? (
        isAuthenticated ? (
          <>
            <div className="project-grid-share-note">
              <label className="project-grid-share-note-label" htmlFor="past-project-share-name">
                Name this shared link
              </label>
              <input
                id="past-project-share-name"
                type="text"
                className="project-grid-share-name-input"
                value={nameDraft}
                maxLength={200}
                placeholder="e.g. Spring 2025 finalists"
                onChange={(event) => setNameDraft(event.target.value)}
              />
            </div>
            <div className="project-grid-share-note">
              <RichTextDetailEditor
                id="past-project-share-note"
                label="Add a note (shown at the top of the shared page)"
                value={noteDraft}
                placeholder="Optional — add context for whoever opens the shared link."
                headerAction={
                  <ProjectNoteInsertControl
                    rows={visibleRows}
                    excludedFields={excludedProjectNoteInsertFields}
                    onInsert={handleInsertVisibleProjectsIntoNote}
                    onToggleExcludedField={handleToggleProjectNoteInsertField}
                  />
                }
                onChange={setNoteDraft}
              />
            </div>
          </>
        ) : (
          <p className="project-grid-share-login-hint">
            <a href={buildLoginPath(`${window.location.pathname}${window.location.search}`)}>Log in</a> to create a
            shareable link.
          </p>
        )
      ) : null}

      {sharedMode ? null : shareResultPanel}

      <ProjectGridTable
        columns={PAST_PROJECT_GRID_COLUMNS}
        rows={rows}
        pagedRows={table.pagedRows}
        filteredCount={table.filteredRows.length}
        totalCount={rows.length}
        search={table.search}
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
        emptyMessage="No merged results saved yet."
        countLabel="results"
        onDeleteRow={sharedMode ? (canEditShared ? handleDeleteSharedRow : undefined) : handleDeleteMergedRow}
        toolbarPlacement="bottom"
        toolbar={
          <div className="project-grid-inline-actions project-grid-inline-actions--clustered">
            <div className="project-grid-toolbar-cluster" aria-label="Export">
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void handleExport(exportProjectRowsPdf, 'PDF')}
                disabled={!exportRows.length}
              >
                PDF
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void handleExport(exportProjectRowsExcel, 'Excel')}
                disabled={!exportRows.length}
              >
                Excel
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => void handleExport(exportProjectRowsWord, 'Microsoft Word')}
                disabled={!exportRows.length}
              >
                Microsoft Word
              </button>
            </div>
            {canShare ? (
              <div className="project-grid-toolbar-cluster" aria-label="Share link">
                <button
                  type="button"
                  className="itg-btn itg-btn-primary"
                  onClick={() => void handleCreateShare()}
                  disabled={!visibleRows.length || isSharing || !nameDraft.trim()}
                >
                  {isSharing ? 'Creating URL...' : 'Get Shareable URL'}
                </button>
              </div>
            ) : null}
          </div>
        }
      />

      {statusMessage ? <p className="project-grid-status">{statusMessage}</p> : null}
    </section>
  );
};
