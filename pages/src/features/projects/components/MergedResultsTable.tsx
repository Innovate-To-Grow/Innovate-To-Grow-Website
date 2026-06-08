import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {ProjectGridTable} from './ProjectGridTable';
import {
  exportProjectRowsExcel,
  exportProjectRowsPdf,
  exportProjectRowsWord,
  type ProjectRowsExporter,
} from './export';
import {useProjectGridTable} from './useProjectGridTable';
import {
  hasProjectGridDetails,
  PAST_PROJECT_GRID_COLUMNS,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';
import {RichTextDetailEditor} from './RichTextDetailEditor';
import {RichDetailPreview} from './RichDetailPreview';
import {SharedEditIcon, SharedSaveIcon} from './shareEditorIcons';
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
  // Owner (builder, or shared-page owner) can author per-project curation notes; a shared-page
  // visitor only ever sees the saved notes read-only.
  const canCurate = !sharedMode || canEditShared;

  // Per-row curation edits, keyed by the row's stable __key. Layered over each row's saved
  // `curation` so typing never mutates the row identity (curation is excluded from the
  // fingerprint/__key) and a draft survives a later builder merge (this component stays mounted).
  const [curationByKey, setCurationByKey] = useState<Record<string, string>>({});

  const effectiveCuration = (item: ProjectGridItem) => curationByKey[item.__key] ?? item.curation ?? '';
  // Stable across renders so it doesn't churn the table hook's expandableKeys memo. Owners can
  // always open a row to add a note; a read-only visitor can only open rows with something to
  // show (abstract/students, or a saved note — visitors never have draft overlay entries).
  const isRowExpandable = useCallback(
    (row: ProjectGridItem) =>
      canCurate ? true : hasProjectGridDetails(row) || Boolean((row.curation ?? '').trim()),
    [canCurate],
  );

  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    expandAllByDefault: sharedMode,
    isRowExpandable,
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
  const editTitleInputRef = useRef<HTMLInputElement>(null);
  const editNoteTextareaRef = useRef<HTMLTextAreaElement>(null);
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

  // Keep the curation overlay in sync with the rows prop. In shared mode a rows change means a
  // save→refetch (or row add/remove), so reseed from the server and drop drafts. In builder mode
  // prune only orphaned keys (deleted rows) so edits for surviving rows persist across a merge.
  useEffect(() => {
    if (sharedMode) {
      setCurationByKey({});
      return;
    }
    setCurationByKey((current) => {
      const liveKeys = new Set(rows.map((row) => row.__key));
      const next: Record<string, string> = {};
      for (const key of Object.keys(current)) {
        if (liveKeys.has(key)) {
          next[key] = current[key];
        }
      }
      return Object.keys(next).length === Object.keys(current).length ? current : next;
    });
  }, [rows, sharedMode]);

  useEffect(() => {
    if (isEditingSharedTitle) {
      editTitleInputRef.current?.focus();
      editTitleInputRef.current?.select();
    }
  }, [isEditingSharedTitle]);

  useEffect(() => {
    if (isEditingSharedNote) {
      editNoteTextareaRef.current?.focus();
    }
  }, [isEditingSharedNote]);

  const withCuration = useCallback(
    (item: ProjectGridItem): ProjectGridRow => {
      const row = stripProjectGridItem(item);
      const override = curationByKey[item.__key];
      return override === undefined ? row : {...row, curation: override};
    },
    [curationByKey],
  );

  // Server truth (no draft overlay) — used by title/note/delete saves so they never silently
  // persist unsaved curation edits.
  const currentRows = useMemo(() => rows.map(stripProjectGridItem), [rows]);
  // With the draft overlay applied — used for curation save, share create, and exports.
  const curatedRows = useMemo(() => rows.map(withCuration), [rows, withCuration]);
  const visibleCuratedRows = useMemo(() => table.sortedRows.map(withCuration), [table.sortedRows, withCuration]);

  const isCurationDirty = useMemo(
    () =>
      rows.some((item) => {
        const override = curationByKey[item.__key];
        return override !== undefined && override !== (item.curation ?? '');
      }),
    [rows, curationByKey],
  );

  const sharedNote = sharedMode ? (note ?? '').trim() : '';
  const sharedExportTitle = (canEditShared ? editTitleDraft : title).trim() || title;
  const sharedExportNote = canEditShared ? editNoteDraft.trim() : sharedNote;
  const sharedExportFileBaseName = getExportFileBaseName(sharedExportTitle);
  const exportTitle = sharedMode ? sharedExportTitle : title;
  const exportNote = sharedMode ? sharedExportNote : '';
  const exportFileBaseName = sharedMode ? sharedExportFileBaseName : 'past-projects';
  // In shared mode the export represents the whole shared snapshot, so a viewer's transient table
  // search must not narrow it. In builder mode the visible (filtered) rows ARE the curation.
  const exportRows = sharedMode ? curatedRows : visibleCuratedRows;
  const exportContext = {
    note: exportNote,
    title: exportTitle,
  };

  const handleCurationChange = (rowKey: string, nextValue: string) => {
    setCurationByKey((current) => ({...current, [rowKey]: nextValue}));
  };

  const handleExport = async (exporter: ProjectRowsExporter, label: string) => {
    try {
      await exporter(exportRows, exportFileBaseName, exportContext);
    } catch {
      // Dynamic-import (code-split chunk) or serialization failures otherwise reject silently.
      setStatusMessage(`Unable to export ${label}. Please try again.`);
    }
  };
  const hasTitleChanges = editTitleDraft.trim() !== title.trim();
  const hasNoteChanges = editNoteDraft.trim() !== (note ?? '').trim();

  const handleCreateShare = async () => {
    const trimmedName = nameDraft.trim();
    if (!onCreateShare || !visibleCuratedRows.length || !trimmedName) {
      return;
    }

    // Mirror the backend cap (serializer rejects >1000 rows) with a specific message instead
    // of letting the request fail with the generic error below.
    if (visibleCuratedRows.length > 1000) {
      setStatusMessage('A shared page can include at most 1000 projects. Remove some rows and try again.');
      return;
    }

    setIsSharing(true);
    setStatusMessage('');
    try {
      await onCreateShare(visibleCuratedRows, trimmedName, noteDraft.trim());
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

    // Send the server-truth rows (no curation overlay), so saving the name never silently
    // persists unsaved curation edits made in the row editors.
    const saved = await handleUpdateSharedPage(currentRows, trimmedTitle, note ?? '', 'Name updated.');
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

    // Send the server-truth rows (no curation overlay), so saving the note never silently
    // persists unsaved curation edits made in the row editors.
    const saved = await handleUpdateSharedPage(currentRows, title, editNoteDraft.trim(), 'Note updated.');
    if (saved) {
      setIsEditingSharedNote(false);
    }
  };

  const handleSaveCuration = async () => {
    if (!isCurationDirty) {
      return;
    }
    // Persist every row with its curation overlay applied; the parent refetch reseeds the prop and
    // the rows-change effect clears the draft overlay.
    await handleUpdateSharedPage(curatedRows, title, note ?? '', 'Project notes updated.');
  };

  const handleDeleteSharedRow = async (row: ProjectGridItem) => {
    const rowIndex = rows.findIndex((candidate) => candidate.__key === row.__key);
    if (rowIndex < 0) {
      return;
    }
    const nextRows = currentRows.filter((_, index) => index !== rowIndex);
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

  const sharedEditor = canEditShared ? (
    <div className={`project-grid-share-editor${isEditingSharedNote ? ' is-editing' : ''}`}>
      <div className="project-grid-share-editor-header">
        <label className="project-grid-share-editor-label" htmlFor="past-project-shared-note-editor">
          Note
        </label>
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
      </div>
      <textarea
        ref={editNoteTextareaRef}
        id="past-project-shared-note-editor"
        className="project-grid-share-editor-textarea"
        value={editNoteDraft}
        maxLength={2000}
        rows={3}
        readOnly={!isEditingSharedNote}
        onChange={(event) => setEditNoteDraft(event.target.value)}
      />
    </div>
  ) : null;

  // Per-project detail body injected into each row's expandable area: the Project notes first
  // (editable for owner/builder, read-only preview for a visitor), then a divider, then the
  // read-only abstract / student names below it.
  const renderRowDetail = (row: ProjectGridItem, surface: 'desktop' | 'mobile') => {
    const curation = effectiveCuration(row);
    // The row __key embeds the fingerprint JSON (quotes/brackets), which is not a valid HTML id.
    // Derive a stable slug-safe id from the row position + surface (desktop and mobile both render
    // a copy, so the id must differ between them to stay unique).
    const rowIndex = rows.findIndex((candidate) => candidate.__key === row.__key);
    const editorId = `past-project-curation-${surface}-${rowIndex}`;
    const curationBlock = canCurate ? (
      <div className="project-grid-row-curation">
        <RichTextDetailEditor
          id={editorId}
          label="Project notes"
          value={curation}
          placeholder="Add a note for this project (optional)."
          onChange={(nextValue) => handleCurationChange(row.__key, nextValue)}
        />
      </div>
    ) : curation.trim() ? (
      <div className="project-grid-row-curation">
        <p className="project-grid-shared-note-label">Project notes</p>
        <RichDetailPreview className="project-grid-shared-detail-text" html={curation} />
      </div>
    ) : null;

    const hasReadOnlyFields = Boolean(row.abstract || row.student_names);

    return (
      <>
        {curationBlock}
        {curationBlock && hasReadOnlyFields ? <hr className="project-grid-row-detail-divider" /> : null}
        {row.abstract ? (
          <div>
            <strong>Abstract:</strong> {row.abstract}
          </div>
        ) : null}
        {row.student_names ? (
          <div>
            <strong>Student Names:</strong> {row.student_names}
          </div>
        ) : null}
      </>
    );
  };

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

      {!sharedEditor && sharedNote ? (
        <div className="project-grid-shared-note">
          <p className="project-grid-shared-note-label">Note</p>
          <p className="project-grid-shared-note-text">{sharedNote}</p>
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
              <label className="project-grid-share-note-label" htmlFor="past-project-share-note">
                Add a note (shown at the top of the shared page)
              </label>
              <textarea
                id="past-project-share-note"
                className="project-grid-share-note-input"
                value={noteDraft}
                maxLength={2000}
                rows={3}
                placeholder="Optional — add context for whoever opens the shared link."
                onChange={(event) => setNoteDraft(event.target.value)}
              />
            </div>
          </>
        ) : (
          <p className="project-grid-share-login-hint">
            <a href="/login">Log in</a> to create a shareable link.
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
        renderRowDetail={renderRowDetail}
        detailExpandable={isRowExpandable}
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
            {canEditShared && isCurationDirty ? (
              <div className="project-grid-toolbar-cluster" aria-label="Save notes">
                <button
                  type="button"
                  className="itg-btn itg-btn-primary"
                  onClick={() => void handleSaveCuration()}
                  disabled={isSavingShareEdit}
                >
                  {isSavingShareEdit ? 'Saving...' : 'Save Project Notes'}
                </button>
              </div>
            ) : null}
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
                  disabled={!visibleCuratedRows.length || isSharing || !nameDraft.trim()}
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
