import {useCallback, useEffect, useMemo, useRef, useState, type ReactNode} from 'react';
import {ProjectGridTable} from './ProjectGridTable';
import {useProjectGridTable} from './useProjectGridTable';
import {PastProjectsAIStatus, type PastProjectsStatusTone} from './builder/PastProjectsAIStatus';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

/** Outcome of saving a table's checked rows, shown inside the table that saved them. */
export interface SearchTableSaveResult {
  tone: Exclude<PastProjectsStatusTone, 'loading'>;
  message: string;
  /**
   * Indexes into the submitted rows that were not saved and stay checked (e.g. their details failed to load).
   * Every other submitted row is unchecked. An error result without it keeps every submitted row checked.
   */
  retainedIndexes?: number[];
}

export interface SearchTableSaveHelpers {
  /** The table that is saving, so the caller can tell it apart from the others. */
  tableId: string;
  /** Report detail-loading progress while a save runs. */
  reportProgress: (done: number, total: number) => void;
}

type SaveOutcome = SearchTableSaveResult | boolean | void;
type SaveOrigin = 'top' | 'bottom';

interface SearchTableCardProps {
  canRemove: boolean;
  className?: string;
  description?: string;
  emptyMessage?: string;
  initialRows: ProjectGridRow[];
  resultsMotionKey?: string | number;
  searchControl?: ReactNode;
  controlsStatus?: ReactNode;
  tableId: string;
  title: string;
  /** Label for the per-table merge button (e.g. "Save Selected" in the builder). */
  mergeLabel?: string;
  /** Verb for the merge ("Save" -> "Save 120 Projects" in the large-save confirmation). */
  mergeVerb?: string;
  /** Verb shown while that merge runs ("Saving" -> "Saving…" / "Saving 3 projects…"). */
  mergingVerb?: string;
  /** Disable the merge button (e.g. while an async add from another table is in flight). */
  mergeDisabled?: boolean;
  /** Marks rows that are already in the saved results (e.g. with a "Saved" chip). */
  isRowSaved?: (row: ProjectGridRow) => boolean;
  savedRowLabel?: string;
  /** Scroll to the saved results; offered next to a save's outcome. */
  onViewMergedResults?: () => void;
  viewMergedResultsLabel?: string;
  /** Told how many rows this table has checked, so the page can mention selections another table left unsaved. */
  onSelectionCountChange?: (tableId: string, count: number, title: string) => void;
  onRemove: (tableId: string) => void;
  onRefresh?: (tableId: string) => void;
  /**
   * Push this table's checked rows into the merged results. Resolve to a SearchTableSaveResult to report
   * the outcome inside this table; legacy callers may resolve to `false` to keep the whole selection.
   * Submitted rows are unchecked afterwards except the retained ones, so rows checked while a save runs
   * stay checked.
   */
  onMergeSelected: (
    rows: ProjectGridRow[],
    helpers: SearchTableSaveHelpers,
  ) => SaveOutcome | PromiseLike<SaveOutcome>;
}

const SAVE_FAILED_MESSAGE = 'Could not save the selected projects. They are still selected, so you can try again.';
// Saving this many rows at once is almost always an accidental "select everything"; ask first.
const LARGE_SAVE_THRESHOLD = 100;
// Progress is shown for saves that load this many details, updated in tenths so it does not flood.
const PROGRESS_MIN_TOTAL = 20;
// Long pages get a second Save button under the table, where the eye is after checking rows.
const BOTTOM_ACTIONS_MIN_ROWS = 6;

const pluralize = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

const isPromiseLike = <T,>(value: unknown): value is PromiseLike<T> =>
  typeof (value as {then?: unknown} | null | undefined)?.then === 'function';

function SearchTableRemoveIcon() {
  return (
    <svg className="search-table-remove-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M3.75 6.25h16.5" />
      <path d="M9 6.25V4.8c0-.88.72-1.6 1.6-1.6h2.8c.88 0 1.6.72 1.6 1.6v1.45" />
      <path d="m18.75 6.25-.7 12.05a2.05 2.05 0 0 1-2.05 1.95H8a2.05 2.05 0 0 1-2.05-1.95L5.25 6.25" />
      <path d="M10 11v5" />
      <path d="M14 11v5" />
    </svg>
  );
}

export function SearchTableCard({
  canRemove,
  className,
  description = 'Search this table, check the projects you want, then click Save Selected to add them to your saved results.',
  emptyMessage = 'No rows available in this search table.',
  initialRows,
  resultsMotionKey,
  searchControl,
  controlsStatus,
  tableId,
  title,
  mergeLabel = 'Save Selected',
  mergeVerb = 'Save',
  mergingVerb = 'Saving',
  mergeDisabled = false,
  isRowSaved,
  savedRowLabel,
  onViewMergedResults,
  viewMergedResultsLabel = 'View Saved Results',
  onSelectionCountChange,
  onRemove,
  onRefresh,
  onMergeSelected,
}: SearchTableCardProps) {
  const [rows, setRows] = useState<ProjectGridItem[]>(() => createProjectGridItems(initialRows, tableId));
  const [undoRows, setUndoRows] = useState<ProjectGridItem[] | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveProgress, setSaveProgress] = useState<{count: number; done: number; total: number} | null>(null);
  const [saveStatus, setSaveStatus] = useState<SearchTableSaveResult | null>(null);
  const [saveOrigin, setSaveOrigin] = useState<SaveOrigin>('top');
  const [pendingLargeSave, setPendingLargeSave] = useState<{rows: ProjectGridItem[]; origin: SaveOrigin} | null>(null);
  // Rows submitted by the save in flight: still checked, but no longer waiting for the user to save them.
  const [inFlightKeys, setInFlightKeys] = useState<ReadonlySet<string>>(() => new Set());
  const isSavingRef = useRef(false);
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
  });

  const shownKeys = useMemo(() => new Set(table.filteredRows.map((row) => row.__key)), [table.filteredRows]);
  const selectedCount = table.selectedRows.length;
  const hiddenSelectedCount = table.selectedRows.filter((row) => !shownKeys.has(row.__key)).length;
  const unsavedSelectedCount = table.selectedRows.filter((row) => !inFlightKeys.has(row.__key)).length;

  useEffect(() => {
    onSelectionCountChange?.(tableId, unsavedSelectedCount, title);
    return () => onSelectionCountChange?.(tableId, 0, title);
  }, [onSelectionCountChange, unsavedSelectedCount, tableId, title]);

  // A save's outcome stays up until the user starts a new selection in this table.
  const clearSaveStatus = () => setSaveStatus(null);

  const handleDeleteSelectedRows = useCallback(() => {
    if (!table.hasSelection) {
      return;
    }

    const nextRows = table.removeSelectedRows(rows);
    if (nextRows.length === rows.length) {
      table.clearSelection();
      return;
    }

    setUndoRows(rows);
    setRows(nextRows);
    table.clearSelection();
  }, [rows, table]);

  // Trims the table to the checked rows and keeps them checked, so Save Selected works right away.
  const handleKeepSelectedRows = useCallback(() => {
    if (!table.hasSelection) {
      return;
    }

    const nextRows = table.keepSelectedRows(rows);
    if (nextRows.length === rows.length) {
      return;
    }

    setUndoRows(rows);
    setRows(nextRows);
  }, [rows, table]);

  // Uncheck only what was submitted and not retained: a failed save keeps its rows checked for a retry,
  // and rows checked while the save ran are not wiped.
  const finishSave = useCallback(
    (submitted: ProjectGridItem[], outcome: SaveOutcome) => {
      const keepsAll =
        outcome === false || (typeof outcome === 'object' && outcome.tone === 'error' && !outcome.retainedIndexes);
      const retained = keepsAll
        ? new Set(submitted.map((_, index) => index))
        : new Set(typeof outcome === 'object' ? (outcome.retainedIndexes ?? []) : []);
      table.removeFromSelection(submitted.filter((_, index) => !retained.has(index)).map((row) => row.__key));
      setSaveStatus(typeof outcome === 'object' && outcome.message ? outcome : null);
    },
    [table],
  );

  const runSave = useCallback(
    async (submitted: ProjectGridItem[], origin: SaveOrigin) => {
      const failure: SearchTableSaveResult = {tone: 'error', message: SAVE_FAILED_MESSAGE};
      setSaveOrigin(origin);
      let pending: SaveOutcome | PromiseLike<SaveOutcome>;
      try {
        pending = onMergeSelected(submitted.map(stripProjectGridItem), {
          tableId,
          reportProgress: (done, total) => {
            const step = Math.max(1, Math.floor(total / 10));
            if (total >= PROGRESS_MIN_TOTAL && (done === total || done % step === 0)) {
              setSaveProgress({count: submitted.length, done, total});
            }
          },
        });
      } catch {
        finishSave(submitted, failure);
        return;
      }
      // A save that needs no network finishes in this click; only a pending one shows the in-flight state.
      if (!isPromiseLike<SaveOutcome>(pending)) {
        finishSave(submitted, pending);
        return;
      }

      isSavingRef.current = true;
      setIsSaving(true);
      setInFlightKeys(new Set(submitted.map((row) => row.__key)));
      setSaveStatus(null);
      setSaveProgress({count: submitted.length, done: 0, total: 0});
      let outcome: SaveOutcome;
      try {
        outcome = await pending;
      } catch {
        outcome = failure;
      } finally {
        isSavingRef.current = false;
        setIsSaving(false);
        setInFlightKeys(new Set());
        setSaveProgress(null);
      }
      finishSave(submitted, outcome);
    },
    [finishSave, onMergeSelected, tableId],
  );

  const handleSaveSelectedRows = (origin: SaveOrigin) => {
    if (!table.hasSelection || isSavingRef.current) {
      return;
    }
    const submitted = table.selectedRows;
    if (submitted.length > LARGE_SAVE_THRESHOLD) {
      setPendingLargeSave({rows: submitted, origin});
      return;
    }
    void runSave(submitted, origin);
  };

  const handleUndoLastRowAction = useCallback(() => {
    if (!undoRows) {
      return;
    }

    setRows(undoRows);
    setUndoRows(null);
    table.clearSelection();
  }, [table, undoRows]);

  const handleToggleSelected = (rowKey: string) => {
    clearSaveStatus();
    table.toggleSelected(rowKey);
  };

  // Header checkbox and "Select All" act on the rows the current search shows (all rows when there is
  // no search), never on rows hidden by it, so a filtered "select all, uncheck a few" saves what it shows.
  const handleToggleSelectAllShown = () => {
    clearSaveStatus();
    const shown = table.filteredRows;
    if (shown.length > 0 && shown.every((row) => table.selectedKeys.has(row.__key))) {
      table.removeFromSelection(shown.map((row) => row.__key));
    } else {
      table.addToSelection(shown);
    }
  };

  const saveButton = (origin: SaveOrigin) => (
    <button
      type="button"
      className="itg-btn itg-btn-primary"
      onClick={() => handleSaveSelectedRows(origin)}
      // aria-disabled (not disabled) while saving keeps keyboard focus on the button that was pressed.
      disabled={!isSaving && (!table.hasSelection || mergeDisabled)}
      aria-disabled={isSaving || undefined}
    >
      {isSaving ? `${mergingVerb}…` : mergeLabel}
    </button>
  );

  const selectionCount = selectedCount ? (
    <span className="search-table-selection-count">
      {selectedCount} selected
      {hiddenSelectedCount ? ` (${hiddenSelectedCount} not shown by the current search)` : ''}
    </span>
  ) : null;

  // Screen readers hear outcomes through one persistent polite region per table (errors use an alert);
  // the visible box sits next to the Save button that was pressed.
  const liveText = saveProgress
    ? `${mergingVerb} ${pluralize(saveProgress.count, 'project')}…`
    : saveStatus && saveStatus.tone !== 'error'
      ? saveStatus.message
      : '';
  let visibleStatus: ReactNode = null;
  if (saveProgress) {
    const loaded = saveProgress.total ? ` Loaded details for ${saveProgress.done} of ${saveProgress.total}.` : '';
    visibleStatus = (
      <PastProjectsAIStatus
        announce={false}
        tone="loading"
        message={`${mergingVerb} ${pluralize(saveProgress.count, 'project')}…${loaded}`}
      />
    );
  } else if (saveStatus) {
    visibleStatus = (
      <>
        <PastProjectsAIStatus announce={saveStatus.tone === 'error'} tone={saveStatus.tone} message={saveStatus.message} />
        {onViewMergedResults && saveStatus.tone !== 'error' ? (
          <button type="button" className="past-projects-status-action" onClick={onViewMergedResults}>
            {viewMergedResultsLabel}
          </button>
        ) : null}
      </>
    );
  }
  const statusFor = (origin: SaveOrigin) =>
    visibleStatus && saveOrigin === origin ? <div className="search-table-save-status">{visibleStatus}</div> : null;

  return (
    <section
      className={`project-grid-card search-table-card${className ? ` ${className}` : ''}`}
      data-search-table-id={tableId}
      aria-busy={isSaving}
    >
      <div className="project-grid-card-header">
        <div>
          <h3 className="project-grid-card-title">{title}</h3>
          <p className="project-grid-card-copy">{description}</p>
        </div>
        {canRemove ? (
          <button
            type="button"
            className="search-table-remove-button"
            aria-label={`Delete ${title}`}
            title={`Delete ${title}`}
            onClick={() => onRemove(tableId)}
            disabled={isSaving}
          >
            <SearchTableRemoveIcon />
          </button>
        ) : null}
      </div>

      <p className="sr-only" role="status" aria-live="polite">
        {liveText}
      </p>

      <div
        key={resultsMotionKey === undefined ? 'search-table-static-results' : `search-table-results-${resultsMotionKey}`}
        className={resultsMotionKey ? 'search-table-results-motion' : undefined}
      >
        <ProjectGridTable
          loadMissingDetails
          columns={PAST_PROJECT_GRID_COLUMNS}
          rows={rows}
          pagedRows={table.pagedRows}
          filteredCount={table.filteredRows.length}
          totalCount={rows.length}
          search={table.search}
          searchControl={searchControl}
          controlsStatus={controlsStatus}
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
          emptyMessage={emptyMessage}
          countLabel="entries"
          selectable
          selectedKeys={table.selectedKeys}
          selectAllStateRows={table.filteredRows}
          onToggleSelected={handleToggleSelected}
          onToggleSelectAll={handleToggleSelectAllShown}
          isRowSaved={isRowSaved}
          savedRowLabel={savedRowLabel}
          toolbar={
            <div className="project-grid-inline-actions project-grid-inline-actions--clustered">
              <div className="project-grid-toolbar-cluster" aria-label="Save">
                {saveButton('top')}
                {selectionCount}
              </div>
              {statusFor('top')}
              <div className="project-grid-toolbar-cluster" aria-label="Table rows">
                <button
                  type="button"
                  className="itg-btn itg-btn-outline"
                  onClick={handleDeleteSelectedRows}
                  disabled={!table.hasSelection || isSaving}
                >
                  Remove from Table
                </button>
                <button
                  type="button"
                  className="itg-btn itg-btn-outline"
                  onClick={handleKeepSelectedRows}
                  disabled={!table.hasSelection || isSaving}
                >
                  Keep Only Selected
                </button>
                <button
                  type="button"
                  className="itg-btn itg-btn-outline"
                  onClick={handleUndoLastRowAction}
                  disabled={!undoRows || isSaving}
                >
                  Undo Row Change
                </button>
              </div>
              <div className="project-grid-toolbar-cluster" aria-label="Selection">
                <button
                  type="button"
                  className="itg-btn itg-btn-outline"
                  onClick={() => {
                    clearSaveStatus();
                    table.addToSelection(table.filteredRows);
                  }}
                  disabled={!table.filteredRows.length}
                >
                  Select All
                </button>
                <button
                  type="button"
                  className="itg-btn itg-btn-outline"
                  onClick={() => {
                    clearSaveStatus();
                    table.clearSelection();
                  }}
                  disabled={!table.hasSelection}
                >
                  Deselect
                </button>
                {onRefresh ? (
                  <button
                    type="button"
                    className="itg-btn itg-btn-outline"
                    onClick={() => onRefresh(tableId)}
                    disabled={isSaving}
                  >
                    Refresh Search Table
                  </button>
                ) : null}
              </div>
            </div>
          }
        />
        {table.pagedRows.length >= BOTTOM_ACTIONS_MIN_ROWS ? (
          <div className="search-table-bottom-actions" role="group" aria-label={`Save from ${title}`}>
            <div className="project-grid-toolbar-cluster">
              {saveButton('bottom')}
              {selectionCount}
            </div>
            {statusFor('bottom')}
          </div>
        ) : null}
      </div>

      {pendingLargeSave ? (
        <PastProjectsDialog
          title={`${mergeVerb} ${pluralize(pendingLargeSave.rows.length, 'project')}?`}
          confirmLabel={`${mergeVerb} ${pluralize(pendingLargeSave.rows.length, 'Project')}`}
          onCancel={() => setPendingLargeSave(null)}
          onConfirm={() => {
            const {rows: submitted, origin} = pendingLargeSave;
            setPendingLargeSave(null);
            void runSave(submitted, origin);
          }}
        >
          <p>
            {hiddenSelectedCount
              ? `${hiddenSelectedCount} of them are not shown by the current search. `
              : ''}
            Each project&apos;s details are loaded first, which can take a while. Did you mean to select this many?
          </p>
        </PastProjectsDialog>
      ) : null}
    </section>
  );
}
