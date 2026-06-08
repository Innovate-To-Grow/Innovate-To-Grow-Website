import {type ClipboardEvent, type ReactNode, useEffect, useMemo, useRef, useState} from 'react';
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
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';
import {
  copyPastProjectsDetailToClipboard,
  createPastProjectsDetailHtml,
  normalizePastProjectsDetailHtml,
  sanitizePastProjectsDetailHtml,
} from './pastProjectsDetailText';

interface MergedResultsTableProps {
  rows: ProjectGridItem[];
  sharedMode?: boolean;
  title?: string;
  note?: string;
  detailsText?: string;
  editable?: boolean;
  onCreateShare?: (
    rows: ProjectGridRow[],
    name: string,
    note: string,
    detailsText: string,
  ) => Promise<PastProjectShareCreationResult>;
  onUpdateShare?: (rows: ProjectGridRow[], note: string, name: string, detailsText: string) => Promise<void>;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

export type PastProjectShareCreationResult =
  | string
  | {
      id: string;
      share_url?: string;
    };

interface RichDetailPreviewProps {
  html: string;
  className?: string;
}

function RichDetailPreview({html, className}: RichDetailPreviewProps) {
  const ref = useRef<HTMLDivElement>(null);
  const sanitizedHtml = useMemo(() => sanitizePastProjectsDetailHtml(html), [html]);

  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = sanitizedHtml;
    }
  }, [sanitizedHtml]);

  return <div ref={ref} className={className} />;
}

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

function HighlighterIcon() {
  return (
    <svg className="project-grid-rich-editor-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m4.75 14.25 8.9-8.9 4.9 4.9-8.9 8.9H4.75v-4.9Z" />
      <path d="m12.35 6.65 4 4" />
      <path d="M3.75 20.25h9.5" />
    </svg>
  );
}

function ClearFormattingIcon() {
  return (
    <svg className="project-grid-rich-editor-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m5.25 14.25 8.5-8.5a2.12 2.12 0 0 1 3 0l1.5 1.5a2.12 2.12 0 0 1 0 3l-8.5 8.5H5.25v-4.5Z" />
      <path d="m12.25 7.75 4.5 4.5" />
      <path d="M4.75 20.25h14.5" />
    </svg>
  );
}

interface RichTextDetailEditorProps {
  id: string;
  label: string;
  value: string;
  placeholder?: string;
  readOnly?: boolean;
  autoFocus?: boolean;
  isLargeDetailSet?: boolean;
  projectCount?: number;
  headerAction?: ReactNode;
  onCopyAll?: () => void;
  onChange: (value: string) => void;
}

function RichTextDetailEditor({
  id,
  label,
  value,
  placeholder = '',
  readOnly = false,
  autoFocus = false,
  isLargeDetailSet = false,
  projectCount,
  headerAction,
  onCopyAll,
  onChange,
}: RichTextDetailEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const labelId = `${id}-label`;
  const sanitizedValue = useMemo(() => sanitizePastProjectsDetailHtml(value), [value]);
  const editorClassName = `project-grid-rich-detail-editor${isLargeDetailSet ? ' is-large-detail-set' : ''}`;
  const inputClassName = `project-grid-rich-detail-input${isLargeDetailSet ? ' is-large-detail-set' : ''}`;

  useEffect(() => {
    if (!editorRef.current || editorRef.current.innerHTML === sanitizedValue) {
      return;
    }
    editorRef.current.innerHTML = sanitizedValue;
  }, [sanitizedValue]);

  useEffect(() => {
    if (autoFocus && !readOnly) {
      editorRef.current?.focus();
    }
  }, [autoFocus, readOnly]);

  const emitChange = () => {
    onChange(sanitizePastProjectsDetailHtml(editorRef.current?.innerHTML ?? ''));
  };

  const applyCommand = (command: string, commandValue?: string) => {
    if (readOnly) {
      return;
    }

    editorRef.current?.focus();
    if (typeof document.execCommand === 'function') {
      document.execCommand(command, false, commandValue);
    }
    emitChange();
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    if (readOnly) {
      return;
    }

    event.preventDefault();
    const plainText = event.clipboardData.getData('text/plain');
    if (typeof document.execCommand === 'function') {
      document.execCommand('insertText', false, plainText);
    }
    emitChange();
  };

  return (
    <div className={editorClassName} data-project-count={projectCount}>
      <div className="project-grid-rich-detail-header">
        <label id={labelId} className="project-grid-share-note-label" htmlFor={id}>
          {label}
        </label>
        {!readOnly || headerAction || onCopyAll ? (
          <div className="project-grid-rich-detail-controls">
            {onCopyAll ? (
              <button type="button" className="project-grid-rich-copy-button" onClick={onCopyAll}>
                Copy All
              </button>
            ) : null}
            {!readOnly ? (
              <div className="project-grid-rich-detail-toolbar" aria-label={`${label} formatting`}>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Bold"
                  title="Bold"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('bold')}
                >
                  <strong>B</strong>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Italic"
                  title="Italic"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('italic')}
                >
                  <em>I</em>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Highlight"
                  title="Highlight"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('hiliteColor', '#fff3a3')}
                >
                  <HighlighterIcon />
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Clear formatting"
                  title="Clear formatting"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('removeFormat')}
                >
                  <ClearFormattingIcon />
                </button>
              </div>
            ) : null}
            {headerAction}
          </div>
        ) : null}
      </div>
      <div
        ref={editorRef}
        id={id}
        className={inputClassName}
        role="textbox"
        aria-labelledby={labelId}
        aria-multiline="true"
        aria-readonly={readOnly}
        contentEditable={!readOnly}
        data-placeholder={placeholder}
        spellCheck
        tabIndex={readOnly ? -1 : 0}
        onInput={emitChange}
        onBlur={emitChange}
        onPaste={handlePaste}
        suppressContentEditableWarning
      />
    </div>
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
  detailsText = '',
  editable = false,
  onCreateShare,
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
  const [statusMessage, setStatusMessage] = useState('');
  const [isSharing, setIsSharing] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [detailsDraft, setDetailsDraft] = useState(() =>
    sharedMode ? normalizePastProjectsDetailHtml(detailsText) : createPastProjectsDetailHtml(rows.map(stripProjectGridItem)),
  );
  const [isDetailsTextDirty, setIsDetailsTextDirty] = useState(false);
  const [editTitleDraft, setEditTitleDraft] = useState(title);
  const [editNoteDraft, setEditNoteDraft] = useState(note ?? '');
  const [isSavingShareEdit, setIsSavingShareEdit] = useState(false);
  const [isEditingSharedTitle, setIsEditingSharedTitle] = useState(false);
  const [isEditingSharedNote, setIsEditingSharedNote] = useState(false);
  const [isEditingSharedDetails, setIsEditingSharedDetails] = useState(false);
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
    if (!sharedMode) {
      return;
    }
    setDetailsDraft(normalizePastProjectsDetailHtml(detailsText));
    setIsDetailsTextDirty(false);
    setIsEditingSharedDetails(false);
  }, [detailsText, sharedMode]);

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

  const visibleRows = useMemo(() => table.sortedRows.map(stripProjectGridItem), [table.sortedRows]);
  const generatedDetailsHtml = useMemo(() => createPastProjectsDetailHtml(visibleRows), [visibleRows]);
  const detailProjectCount = sharedMode ? currentRows.length : visibleRows.length;
  const isLargeDetailSet = detailProjectCount > 12;

  useEffect(() => {
    if (sharedMode || isDetailsTextDirty) {
      return;
    }
    setDetailsDraft(generatedDetailsHtml);
  }, [generatedDetailsHtml, isDetailsTextDirty, sharedMode]);

  const canShare = !sharedMode && Boolean(onCreateShare) && isAuthenticated;
  const canEditShared = sharedMode && editable && Boolean(onUpdateShare);
  const sharedNote = sharedMode ? (note ?? '').trim() : '';
  const sharedDetails = sharedMode ? detailsDraft.trim() : '';
  const sharedExportTitle = (canEditShared ? editTitleDraft : title).trim() || title;
  const sharedExportNote = canEditShared ? editNoteDraft.trim() : sharedNote;
  const sharedExportFileBaseName = getExportFileBaseName(sharedExportTitle);
  const hasTitleChanges = editTitleDraft.trim() !== title.trim();
  const hasNoteChanges = editNoteDraft.trim() !== (note ?? '').trim();
  const hasDetailsChanges = detailsDraft !== normalizePastProjectsDetailHtml(detailsText);

  const handleDetailsDraftChange = (nextValue: string) => {
    setDetailsDraft(nextValue);
    setIsDetailsTextDirty(true);
  };

  const handleCopyDetails = async () => {
    if (!detailsDraft.trim()) {
      return;
    }

    try {
      await copyPastProjectsDetailToClipboard(detailsDraft);
      setStatusMessage('Past Projects Detail copied.');
    } catch {
      setStatusMessage('Unable to copy Past Projects Detail. Please try again.');
    }
  };

  const handleCreateShare = async () => {
    const trimmedName = nameDraft.trim();
    if (!onCreateShare || !visibleRows.length || !trimmedName) {
      return;
    }

    setIsSharing(true);
    setStatusMessage('');
    try {
      await onCreateShare(visibleRows, trimmedName, noteDraft.trim(), detailsDraft);
      if (isMountedRef.current) {
        setStatusMessage('Opening shareable link...');
      }
    } catch {
      if (isMountedRef.current) {
        setStatusMessage('Unable to create a shareable URL. Please try again.');
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
    nextDetailsText: string,
    successMessage: string,
  ) => {
    if (!onUpdateShare) {
      return false;
    }

    setIsSavingShareEdit(true);
    setStatusMessage('');
    try {
      await onUpdateShare(nextRows, nextNote, nextName, nextDetailsText);
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
      setIsEditingSharedDetails(false);
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

    const saved = await handleUpdateSharedPage(currentRows, note ?? '', trimmedTitle, detailsDraft, 'Name updated.');
    if (saved) {
      setIsEditingSharedTitle(false);
    }
  };

  const handleSharedNoteAction = async () => {
    if (!isEditingSharedNote) {
      setIsEditingSharedNote(true);
      setIsEditingSharedTitle(false);
      setIsEditingSharedDetails(false);
      return;
    }

    if (!hasNoteChanges) {
      setIsEditingSharedNote(false);
      return;
    }

    const saved = await handleUpdateSharedPage(currentRows, editNoteDraft.trim(), title, detailsDraft, 'Note updated.');
    if (saved) {
      setIsEditingSharedNote(false);
    }
  };

  const handleSharedDetailsAction = async () => {
    if (!isEditingSharedDetails) {
      setIsEditingSharedDetails(true);
      setIsEditingSharedTitle(false);
      setIsEditingSharedNote(false);
      return;
    }

    if (!hasDetailsChanges) {
      setIsEditingSharedDetails(false);
      return;
    }

    const saved = await handleUpdateSharedPage(
      currentRows,
      note ?? '',
      title,
      detailsDraft,
      'Past projects detail updated.',
    );
    if (saved) {
      setIsEditingSharedDetails(false);
      setIsDetailsTextDirty(false);
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
    await handleUpdateSharedPage(nextRows, note ?? '', title, detailsDraft, 'Project removed.');
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

  const sharedDetailsEditor = canEditShared ? (
    <div className={`project-grid-share-editor${isEditingSharedDetails ? ' is-editing' : ''}`}>
      <RichTextDetailEditor
        id="past-project-shared-details-editor"
        label="Past Projects Detail"
        value={detailsDraft}
        readOnly={!isEditingSharedDetails}
        autoFocus={isEditingSharedDetails}
        headerAction={
          <button
            type="button"
            className={`project-grid-share-editor-icon-button project-grid-share-details-action${
              isEditingSharedDetails ? ' is-active' : ''
            }`}
            aria-label={isEditingSharedDetails ? 'Save Past Projects Detail' : 'Edit Past Projects Detail'}
            title={isEditingSharedDetails ? 'Save Past Projects Detail' : 'Edit Past Projects Detail'}
            onClick={() => void handleSharedDetailsAction()}
            disabled={isSavingShareEdit}
          >
            {isEditingSharedDetails ? <SharedSaveIcon /> : <SharedEditIcon />}
          </button>
        }
        placeholder="Selected project details will appear here."
        isLargeDetailSet={isLargeDetailSet}
        projectCount={detailProjectCount}
        onCopyAll={() => void handleCopyDetails()}
        onChange={handleDetailsDraftChange}
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

      {sharedDetailsEditor}

      {!sharedDetailsEditor && sharedDetails ? (
        <div className="project-grid-shared-detail">
          <div className="project-grid-shared-detail-header">
            <p className="project-grid-shared-note-label">Past Projects Detail</p>
            <button type="button" className="project-grid-rich-copy-button" onClick={() => void handleCopyDetails()}>
              Copy All
            </button>
          </div>
          <RichDetailPreview className="project-grid-shared-detail-text" html={sharedDetails} />
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

      {!sharedMode ? (
        <div className="project-grid-share-note">
          <RichTextDetailEditor
            id="past-project-share-details"
            label="Past Projects Detail"
            value={detailsDraft}
            placeholder="Selected project details will appear here."
            isLargeDetailSet={isLargeDetailSet}
            projectCount={detailProjectCount}
            onCopyAll={() => void handleCopyDetails()}
            onChange={handleDetailsDraftChange}
          />
        </div>
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
