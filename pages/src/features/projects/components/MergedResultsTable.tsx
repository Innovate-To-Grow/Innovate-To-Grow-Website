import {useEffect, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {ProjectGridTable} from './ProjectGridTable';
import {
  exportProjectRowsCsv,
  exportProjectRowsExcel,
  exportProjectRowsPdf,
  exportSharedProjectRowsExcel,
  exportSharedProjectRowsPdf,
  exportSharedProjectRowsWord,
} from './projectGridExport';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridFingerprint,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

interface MergedResultsTableProps {
  rows: ProjectGridItem[];
  sharedMode?: boolean;
  title?: string;
  note?: string;
  editable?: boolean;
  onCreateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<PastProjectShareCreationResult>;
  onUpdateCreatedShare?: (shareId: string, rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  onUpdateShare?: (rows: ProjectGridRow[], note: string, name: string) => Promise<void>;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

export type PastProjectShareCreationResult =
  | string
  | {
      id: string;
      share_url?: string;
    };

interface CreatedPastProjectShare {
  id: string;
  url: string;
}

const toCreatedPastProjectShare = (result: PastProjectShareCreationResult): CreatedPastProjectShare | null => {
  if (typeof result === 'string') {
    return null;
  }

  return {
    id: result.id,
    url: new URL(`/past-projects/${result.id}`, window.location.origin).toString(),
  };
};

const removeProjectGridRow = (sourceRows: ProjectGridRow[], row: ProjectGridRow) => {
  const rowFingerprint = createProjectGridFingerprint(row);
  let hasRemovedRow = false;

  return sourceRows.filter((sourceRow) => {
    if (!hasRemovedRow && createProjectGridFingerprint(sourceRow) === rowFingerprint) {
      hasRemovedRow = true;
      return false;
    }

    return true;
  });
};

function SharedEditIcon() {
  return (
    <svg className="project-grid-share-editor-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M4.75 19.25h3.4L18.2 9.2a2.4 2.4 0 0 0 0-3.4l-.55-.55a2.4 2.4 0 0 0-3.4 0L4.75 14.75v4.5Z" />
      <path d="m13.15 6.35 3.5 3.5" />
    </svg>
  );
}

function SharedSaveIcon() {
  return (
    <svg className="project-grid-share-editor-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 4.75h12.2L19.25 7v12.25H4.75V4.75Z" />
      <path d="M8 4.75v5h8v-5" />
      <path d="M8 19.25v-6h8v6" />
    </svg>
  );
}

const getExportFileBaseName = (title: string) => {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug ? `past-projects-${slug}` : 'past-projects';
};

export const MergedResultsTable = ({
  rows,
  sharedMode = false,
  title = 'Saved Merged Results',
  note,
  editable = false,
  onCreateShare,
  onUpdateCreatedShare,
  onUpdateShare,
  onDeleteRow,
}: MergedResultsTableProps) => {
  const {isAuthenticated} = useAuth();
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    expandAllByDefault: sharedMode,
  });
  const [shareUrl, setShareUrl] = useState('');
  const [createdShare, setCreatedShare] = useState<CreatedPastProjectShare | null>(null);
  const [createdShareRows, setCreatedShareRows] = useState<ProjectGridRow[] | null>(null);
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

  useEffect(() => {
    if (isEditingSharedNote) {
      editNoteTextareaRef.current?.focus();
    }
  }, [isEditingSharedNote]);

  const currentRows = useMemo(() => rows.map(stripProjectGridItem), [rows]);

  const visibleRows = table.sortedRows.map(stripProjectGridItem);
  const canShare = !sharedMode && Boolean(onCreateShare) && isAuthenticated;
  const canEditShared = sharedMode && editable && Boolean(onUpdateShare);
  const sharedNote = sharedMode ? (note ?? '').trim() : '';
  const sharedExportTitle = (canEditShared ? editTitleDraft : title).trim() || title;
  const sharedExportNote = canEditShared ? editNoteDraft.trim() : sharedNote;
  const sharedExportFileBaseName = getExportFileBaseName(sharedExportTitle);
  const hasTitleChanges = editTitleDraft.trim() !== title.trim();
  const hasNoteChanges = editNoteDraft.trim() !== (note ?? '').trim();

  const handleCreateShare = async () => {
    const trimmedName = nameDraft.trim();
    if (!onCreateShare || !visibleRows.length || !trimmedName) {
      return;
    }

    setIsSharing(true);
    setStatusMessage('');
    try {
      const nextShare = await onCreateShare(visibleRows, trimmedName, noteDraft.trim());
      const created = toCreatedPastProjectShare(nextShare);
      setCreatedShare(created);
      setCreatedShareRows(created ? visibleRows : null);
      setShareUrl(created?.url ?? String(nextShare));
      setStatusMessage('Shareable URL is ready below.');
    } catch {
      setStatusMessage('Unable to create a shareable URL. Please try again.');
    } finally {
      setIsSharing(false);
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
        setStatusMessage('URL copied to clipboard.');
        return;
      }
    } catch {
      // Fall through to the selected-input copy fallback below.
    }

    try {
      if (document.execCommand('copy')) {
        setStatusMessage('URL copied to clipboard.');
        return;
      }
    } catch {
      // Keep the final fallback message below.
    }

    setStatusMessage('Unable to copy URL. Select the link and copy it manually.');
  };

  const handleUpdateSharedPage = async (
    nextRows: ProjectGridRow[],
    nextNote: string,
    nextName: string,
    successMessage: string,
  ) => {
    if (!onUpdateShare) {
      return false;
    }

    setIsSavingShareEdit(true);
    setStatusMessage('');
    try {
      await onUpdateShare(nextRows, nextNote, nextName);
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

    const saved = await handleUpdateSharedPage(currentRows, note ?? '', trimmedTitle, 'Name updated.');
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

    const saved = await handleUpdateSharedPage(currentRows, editNoteDraft.trim(), title, 'Note updated.');
    if (saved) {
      setIsEditingSharedNote(false);
    }
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
    await handleUpdateSharedPage(nextRows, note ?? '', title, 'Project removed.');
  };

  const handleDeleteMergedRow = async (row: ProjectGridItem) => {
    if (!onDeleteRow) {
      return;
    }

    const rowIndex = rows.findIndex((candidate) => candidate.__key === row.__key);
    if (rowIndex < 0) {
      return;
    }

    if (createdShare && onUpdateCreatedShare) {
      const nextShareRows = removeProjectGridRow(createdShareRows ?? currentRows, stripProjectGridItem(row));
      if (nextShareRows.length === (createdShareRows ?? currentRows).length) {
        onDeleteRow(row);
        setStatusMessage('Project removed.');
        return;
      }

      if (!nextShareRows.length) {
        setStatusMessage('A shareable link needs at least one project.');
        return;
      }

      setIsSavingShareEdit(true);
      setStatusMessage('');
      try {
        await onUpdateCreatedShare(createdShare.id, nextShareRows, nameDraft.trim(), noteDraft.trim());
        setCreatedShareRows(nextShareRows);
        onDeleteRow(row);
        setStatusMessage('Project removed from the shareable link.');
      } catch {
        setStatusMessage('Unable to update the shareable link. Please try again.');
      } finally {
        setIsSavingShareEdit(false);
      }
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
              {sharedMode ? (
                <>
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() =>
                      void exportSharedProjectRowsPdf(visibleRows, sharedExportFileBaseName, {
                        note: sharedExportNote,
                        title: sharedExportTitle,
                      })
                    }
                    disabled={!visibleRows.length}
                  >
                    PDF
                  </button>
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() =>
                      void exportSharedProjectRowsWord(visibleRows, sharedExportFileBaseName, {
                        note: sharedExportNote,
                        title: sharedExportTitle,
                      })
                    }
                    disabled={!visibleRows.length}
                  >
                    Microsoft Word
                  </button>
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() =>
                      void exportSharedProjectRowsExcel(visibleRows, sharedExportFileBaseName, {
                        note: sharedExportNote,
                        title: sharedExportTitle,
                      })
                    }
                    disabled={!visibleRows.length}
                  >
                    Excel
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() => void exportProjectRowsCsv(visibleRows, 'past-projects')}
                    disabled={!visibleRows.length}
                  >
                    CSV
                  </button>
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() => void exportProjectRowsExcel(visibleRows, 'past-projects')}
                    disabled={!visibleRows.length}
                  >
                    Excel
                  </button>
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() => void exportProjectRowsPdf(visibleRows, 'past-projects', title)}
                    disabled={!visibleRows.length}
                  >
                    PDF
                  </button>
                </>
              )}
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
