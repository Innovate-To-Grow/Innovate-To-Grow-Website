import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode} from 'react';
import {useMediaQuery} from '@/features/layout';
import {ProjectGridTable} from './ProjectGridTable';
import {useProjectGridTable} from './useProjectGridTable';
import {PastProjectsAIStatus, type PastProjectsStatusTone} from './builder/PastProjectsAIStatus';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  createProjectGridRowMatcher,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';
import {pluralize} from './saveResults';

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

type SaveOutcome = SearchTableSaveResult | void;
type SaveOrigin = 'top' | 'bottom';

interface SearchTableCardProps {
  canRemove: boolean;
  className?: string;
  description?: string;
  emptyMessage?: string;
  initialRows: ProjectGridRow[];
  /** Search to start the table with. */
  initialSearch?: string;
  /**
   * Changing it replaces the rows with `initialRows` and starts the table over (search, sort, selection), as a
   * reload (Refresh, new AI results). A save that is running carries on and reports its outcome here.
   */
  resetKey?: string | number;
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
  /**
   * Told which checked rows this table has not submitted yet, so the page can mention selections another
   * table left unsaved.
   */
  onSelectionChange?: (tableId: string, rows: ProjectGridRow[], title: string) => void;
  onRemove: (tableId: string) => void;
  onRefresh?: (tableId: string) => void;
  /**
   * Push this table's checked rows into the merged results, and resolve to a SearchTableSaveResult to report
   * the outcome inside this table. Submitted rows are unchecked afterwards except the retained ones, so rows
   * checked while a save runs stay checked.
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

const isPromiseLike = <T,>(value: unknown): value is PromiseLike<T> =>
  typeof (value as {then?: unknown} | null | undefined)?.then === 'function';

export function SearchTableCard({
  canRemove,
  className,
  description = 'Search this table, check the projects you want, then click Save Selected to add them to your saved results.',
  emptyMessage = 'No rows available in this search table.',
  initialRows,
  initialSearch,
  resetKey,
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
  onSelectionChange,
  onRemove,
  onRefresh,
  onMergeSelected,
}: SearchTableCardProps) {
  const [rows, setRows] = useState<ProjectGridItem[]>(() => createProjectGridItems(initialRows, tableId));
  const [undoRows, setUndoRows] = useState<ProjectGridItem[] | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveProgress, setSaveProgress] = useState<{count: number; done: number; total: number} | null>(null);
  const [saveStatus, setSaveStatus] = useState<SearchTableSaveResult | null>(null);
  const [appliedResetKey, setAppliedResetKey] = useState(resetKey);
  const [resetCount, setResetCount] = useState(0);
  const [saveOrigin, setSaveOrigin] = useState<SaveOrigin>('top');
  const [pendingLargeSave, setPendingLargeSave] = useState<{rows: ProjectGridItem[]; origin: SaveOrigin} | null>(null);
  // Rows submitted by the save in flight: still checked, but no longer waiting for the user to save them.
  const [inFlightKeys, setInFlightKeys] = useState<ReadonlySet<string>>(() => new Set());
  // Same breakpoint as the stacked table actions in projects.css.
  const isPhone = useMediaQuery('(max-width: 768px)');
  const isSavingRef = useRef(false);
  // The rows and reset count as last rendered, for a save that finishes after a reload replaced the rows.
  const rowsRef = useRef(rows);
  const resetCountRef = useRef(resetCount);
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    initialSearch,
  });

  if (resetKey !== appliedResetKey) {
    setAppliedResetKey(resetKey);
    setResetCount((count) => count + 1);
    setRows(createProjectGridItems(initialRows, tableId));
    setUndoRows(null);
    setPendingLargeSave(null);
    if (!isSaving) {
      setSaveStatus(null);
    }
    table.reset();
  }

  // Synced during commit, so a save resolving right after a reset already sees the new rows.
  useLayoutEffect(() => {
    rowsRef.current = rows;
    resetCountRef.current = resetCount;
  }, [resetCount, rows]);

  const shownKeys = useMemo(() => new Set(table.filteredRows.map((row) => row.__key)), [table.filteredRows]);
  const selectedCount = table.selectedRows.length;
  const hiddenSelectedCount = table.selectedRows.filter((row) => !shownKeys.has(row.__key)).length;
  const pendingSelection = useMemo(
    () => table.selectedRows.filter((row) => !inFlightKeys.has(row.__key)).map(stripProjectGridItem),
    [inFlightKeys, table.selectedRows],
  );

  useEffect(() => {
    onSelectionChange?.(tableId, pendingSelection, title);
    return () => onSelectionChange?.(tableId, [], title);
  }, [onSelectionChange, pendingSelection, tableId, title]);

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
  // and rows checked while the save ran are not wiped. If the table was reloaded meanwhile, the retained rows
  // are checked again among the new rows.
  const finishSave = useCallback(
    (submitted: ProjectGridItem[], outcome: SaveOutcome, startedAtReset: number) => {
      const keepsAll = outcome?.tone === 'error' && !outcome.retainedIndexes;
      const retained = new Set(keepsAll ? submitted.map((_, index) => index) : (outcome?.retainedIndexes ?? []));
      table.removeFromSelection(submitted.filter((_, index) => !retained.has(index)).map((row) => row.__key));
      let message = outcome?.message ?? '';
      if (resetCountRef.current !== startedAtReset && retained.size) {
        const retainedRows = submitted.filter((_, index) => retained.has(index));
        const isRetained = createProjectGridRowMatcher(retainedRows).has;
        const inNewRows = createProjectGridRowMatcher(rowsRef.current).has;
        table.addToSelection(rowsRef.current.filter(isRetained));
        const missing = retainedRows.filter((row) => !inNewRows(row)).length;
        if (missing && message) {
          message += ` ${missing === 1 ? 'One of them is' : `${missing} of them are`} not in the reloaded table.`;
        }
      }
      setSaveStatus(outcome && message ? {...outcome, message} : null);
    },
    [table],
  );

  const runSave = useCallback(
    async (submitted: ProjectGridItem[], origin: SaveOrigin) => {
      const failure: SearchTableSaveResult = {tone: 'error', message: SAVE_FAILED_MESSAGE};
      const startedAtReset = resetCountRef.current;
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
        finishSave(submitted, failure, startedAtReset);
        return;
      }
      // A save that needs no network finishes in this click; only a pending one shows the in-flight state.
      if (!isPromiseLike<SaveOutcome>(pending)) {
        finishSave(submitted, pending, startedAtReset);
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
      finishSave(submitted, outcome, startedAtReset);
    },
    [finishSave, onMergeSelected, tableId],
  );

  const handleSaveSelectedRows = (origin: SaveOrigin) => {
    if (!table.hasSelection || isSavingRef.current || mergeDisabled) {
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
      className="itg-btn itg-btn-primary search-table-save-button"
      onClick={() => handleSaveSelectedRows(origin)}
      // aria-disabled (not disabled) while saving keeps keyboard focus on the button that was pressed.
      disabled={!isSaving && (!table.hasSelection || mergeDisabled)}
      aria-disabled={isSaving || undefined}
    >
      {isSaving ? `${mergingVerb}…` : mergeLabel}
      {!isSaving && selectedCount ? (
        <span className="search-table-save-count" aria-hidden="true">
          {' '}
          · {selectedCount}
        </span>
      ) : null}
    </button>
  );

  const selectionCount = selectedCount ? (
    <span className="search-table-selection-count">
      {selectedCount} selected
      {hiddenSelectedCount ? ` (${hiddenSelectedCount} not shown by the current search)` : ''}
    </span>
  ) : null;

  // Screen readers hear outcomes apart from the visible box, so an outcome is announced wherever (or whether)
  // that box is shown: a persistent polite region, and for errors an alert, which is announced when it appears.
  const progressText = saveProgress ? `${mergingVerb} ${pluralize(saveProgress.count, 'project')}…` : '';
  const politeText = progressText || (saveStatus && saveStatus.tone !== 'error' ? saveStatus.message : '');
  const alertText = !saveProgress && saveStatus?.tone === 'error' ? saveStatus.message : '';
  let visibleStatus: ReactNode = null;
  if (saveProgress) {
    // Counts settled requests, failed ones included, so it reports progress rather than how many loaded.
    const loading = saveProgress.total ? ` Loading details: ${saveProgress.done} of ${saveProgress.total}.` : '';
    visibleStatus = <PastProjectsAIStatus announce={false} tone="loading" message={`${progressText}${loading}`} />;
  } else if (saveStatus) {
    visibleStatus = (
      <>
        <PastProjectsAIStatus announce={false} tone={saveStatus.tone} message={saveStatus.message} />
        {onViewMergedResults && saveStatus.tone !== 'error' ? (
          <button type="button" className="itg-btn itg-btn-text past-projects-status-action" onClick={onViewMergedResults}>
            {viewMergedResultsLabel}
          </button>
        ) : null}
      </>
    );
  }
  // The visible box sits next to the Save button that was pressed, or the top one once the bottom one is gone
  // (the page got shorter than BOTTOM_ACTIONS_MIN_ROWS rows).
  const showBottomActions = table.pagedRows.length >= BOTTOM_ACTIONS_MIN_ROWS;
  const statusOrigin: SaveOrigin = saveOrigin === 'bottom' && showBottomActions ? 'bottom' : 'top';
  const statusFor = (origin: SaveOrigin) =>
    visibleStatus && statusOrigin === origin ? <div className="search-table-save-status">{visibleStatus}</div> : null;

  const tidyActions = (
    <div
      className="project-grid-toolbar-cluster search-table-action-group"
      role="group"
      aria-label="Tidy this table"
    >
      <span className="search-table-group-label" aria-hidden="true">
        Tidy this table
      </span>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        onClick={handleDeleteSelectedRows}
        disabled={!table.hasSelection || isSaving}
      >
        Remove from Table
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        onClick={handleKeepSelectedRows}
        disabled={!table.hasSelection || isSaving}
      >
        Keep Only Selected
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-text"
        onClick={handleUndoLastRowAction}
        disabled={!undoRows || isSaving}
      >
        Undo Row Change
      </button>
      {onRefresh ? (
        <button
          type="button"
          className="itg-btn itg-btn-text"
          onClick={() => onRefresh(tableId)}
          disabled={isSaving}
        >
          Refresh Search Table
        </button>
      ) : null}
    </div>
  );

  return (
    <section
      className={`project-grid-card search-table-card${className ? ` ${className}` : ''}`}
      data-search-table-id={tableId}
      aria-busy={isSaving}
    >
      <div className="project-grid-card-header search-table-card-header">
        <h3 className="project-grid-card-title">{title}</h3>
        {canRemove ? (
          <button
            type="button"
            className="itg-btn itg-btn-text search-table-remove-button"
            aria-label={`Delete table: ${title}`}
            onClick={() => onRemove(tableId)}
            disabled={isSaving}
          >
            Delete table
          </button>
        ) : null}
      </div>
      <p className="project-grid-card-copy">{description}</p>

      <p className="sr-only" role="status" aria-live="polite">
        {politeText}
      </p>
      {alertText ? (
        <p className="sr-only" role="alert">
          {alertText}
        </p>
      ) : null}

      <div
        key={resultsMotionKey === undefined ? 'search-table-static-results' : `search-table-results-${resultsMotionKey}`}
        className={resultsMotionKey ? 'search-table-results-motion' : undefined}
      >
        <ProjectGridTable
          loadMissingDetails
          linkScope="past"
          columns={PAST_PROJECT_GRID_COLUMNS}
          rows={rows}
          pagedRows={table.pagedRows}
          filteredCount={table.filteredRows.length}
          totalCount={rows.length}
          search={table.search}
          searchPlaceholder="Team, project, organization…"
          searchControl={searchControl}
          controlsStatus={controlsStatus}
          // The card is titled with an h3.
          noResultsHeadingLevel={4}
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
          countLabel="projects"
          selectable
          selectedKeys={table.selectedKeys}
          selectAllStateRows={table.filteredRows}
          onToggleSelected={handleToggleSelected}
          onToggleSelectAll={handleToggleSelectAllShown}
          isRowSaved={isRowSaved}
          savedRowLabel={savedRowLabel}
          toolbar={
            <div className="search-table-actions">
              <div className="search-table-save-row">
                <div className="project-grid-toolbar-cluster search-table-save-group" role="group" aria-label="Save">
                  {saveButton('top')}
                  {selectionCount}
                </div>
                {statusFor('top')}
              </div>
              <div className="search-table-secondary-actions">
                <div className="project-grid-toolbar-cluster search-table-action-group" role="group" aria-label="Selection">
                  <span className="search-table-group-label" aria-hidden="true">
                    Selection
                  </span>
                  <button
                    type="button"
                    className="itg-btn itg-btn-text"
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
                    className="itg-btn itg-btn-text"
                    onClick={() => {
                      clearSaveStatus();
                      table.clearSelection();
                    }}
                    disabled={!table.hasSelection}
                  >
                    Deselect
                  </button>
                </div>
                {isPhone ? (
                  // Seven buttons, most of them disabled until rows are checked, would push the results
                  // a full screen down on a phone; the table-tidying ones fold away here.
                  <details className="search-table-more-actions">
                    <summary className="search-table-more-actions-summary">More table actions</summary>
                    {tidyActions}
                  </details>
                ) : (
                  <>
                    <span className="search-table-group-divider" aria-hidden="true" />
                    {tidyActions}
                  </>
                )}
              </div>
            </div>
          }
        />
        {showBottomActions ? (
          <div className="search-table-bottom-actions" role="group" aria-label={`Save from ${title}`}>
            <div className="project-grid-toolbar-cluster search-table-save-group">
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
            if (!mergeDisabled) {
              void runSave(submitted, origin);
            }
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
