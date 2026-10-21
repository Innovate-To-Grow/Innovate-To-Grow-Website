import {useState, type ReactNode} from 'react';
import {useMediaQuery} from '@/features/layout';
import {ProjectGridTable} from './ProjectGridTable';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {PAST_PROJECT_GRID_COLUMNS, type ProjectGridRow} from './projectGrid';
import {pluralize} from './saveResults';
import {SaveStatusAnnouncer, VisibleSaveStatus} from './search/SaveStatus';
import {SaveControls, SearchTableToolbar} from './search/SearchTableToolbar';
import type {MergeSelectedHandler, SaveOrigin} from './search/types';
import {useSearchTableRows} from './search/useSearchTableRows';
import {useSearchTableSave} from './search/useSearchTableSave';
import {useSearchTableSelection} from './search/useSearchTableSelection';

export type {SearchTableSaveHelpers, SearchTableSaveResult} from './search/types';

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
  onMergeSelected: MergeSelectedHandler;
}

// Long pages get a second Save button under the table, where the eye is after checking rows.
const BOTTOM_ACTIONS_MIN_ROWS = 6;

function withCardDefaults({
  description = 'Search this table, check the projects you want, then click Save Selected to add them to your saved results.',
  emptyMessage = 'No rows available in this search table.',
  mergeLabel = 'Save Selected',
  mergeVerb = 'Save',
  mergingVerb = 'Saving',
  mergeDisabled = false,
  viewMergedResultsLabel = 'View Saved Results',
  ...rest
}: SearchTableCardProps) {
  return {...rest, description, emptyMessage, mergeLabel, mergeVerb, mergingVerb, mergeDisabled, viewMergedResultsLabel};
}

type CardProps = ReturnType<typeof withCardDefaults>;
type TableRows = ReturnType<typeof useSearchTableRows>;
type Save = ReturnType<typeof useSearchTableSave>;
type Selection = ReturnType<typeof useSearchTableSelection>;

const SearchTableCardHeader = ({card, isSaving}: {card: CardProps; isSaving: boolean}) => (
  <div className="project-grid-card-header search-table-card-header">
    <h3 className="project-grid-card-title">{card.title}</h3>
    {card.canRemove ? (
      <button
        type="button"
        className="itg-btn itg-btn-text search-table-remove-button"
        aria-label={`Delete table: ${card.title}`}
        onClick={() => card.onRemove(card.tableId)}
        disabled={isSaving}
      >
        Delete table
      </button>
    ) : null}
  </div>
);

/** Confirms saving a large selection, whose details all have to be loaded first. */
const LargeSaveDialog = ({save, mergeVerb, hiddenSelectedCount}: {save: Save; mergeVerb: string; hiddenSelectedCount: number}) =>
  save.pendingLargeSave ? (
    <PastProjectsDialog
      title={`${mergeVerb} ${pluralize(save.pendingLargeSave.rows.length, 'project')}?`}
      confirmLabel={`${mergeVerb} ${pluralize(save.pendingLargeSave.rows.length, 'Project')}`}
      onCancel={save.cancelLargeSave}
      onConfirm={save.confirmLargeSave}
    >
      <p>
        {hiddenSelectedCount ? `${hiddenSelectedCount} of them are not shown by the current search. ` : ''}
        Each project&apos;s details are loaded first, which can take a while. Did you mean to select this many?
      </p>
    </PastProjectsDialog>
  ) : null;

interface SearchTableGridProps {
  card: CardProps;
  tableRows: TableRows;
  selection: Selection;
  toolbar: ReactNode;
}

const SearchTableGrid = ({card, tableRows, selection, toolbar}: SearchTableGridProps) => {
  const {rows, table} = tableRows;
  return (
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
      searchControl={card.searchControl}
      controlsStatus={card.controlsStatus}
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
      emptyMessage={card.emptyMessage}
      countLabel="projects"
      selectable
      selectedKeys={table.selectedKeys}
      selectAllStateRows={table.filteredRows}
      onToggleSelected={selection.handleToggleSelected}
      onToggleSelectAll={selection.handleToggleSelectAllShown}
      isRowSaved={card.isRowSaved}
      savedRowLabel={card.savedRowLabel}
      toolbar={toolbar}
    />
  );
};

/**
 * One search table of the past-projects builder: search the rows, check projects, and save them into the
 * merged results. Its rows (`search/useSearchTableRows`), selection (`search/useSearchTableSelection`) and
 * the save flow (`search/useSearchTableSave`) live in their own hooks.
 */
export function SearchTableCard(props: SearchTableCardProps) {
  const card = withCardDefaults(props);
  const {tableId, title, resetKey, mergeDisabled, mergingVerb} = card;
  const tableRows = useSearchTableRows(card.initialRows, tableId, card.initialSearch);
  const {table} = tableRows;
  const save = useSearchTableSave({tableId, tableRows, mergeDisabled, onMergeSelected: card.onMergeSelected});
  const selection = useSearchTableSelection({table, save, tableId, title, onSelectionChange: card.onSelectionChange});
  const [appliedResetKey, setAppliedResetKey] = useState(resetKey);
  // Same breakpoint as the stacked table actions in projectsResponsive.css.
  const isPhone = useMediaQuery('(max-width: 768px)');

  if (resetKey !== appliedResetKey) {
    setAppliedResetKey(resetKey);
    tableRows.reload(card.initialRows);
    save.onTableReload();
  }

  const saveControls = (origin: SaveOrigin) => (
    <SaveControls
      origin={origin}
      save={save}
      hasSelection={table.hasSelection}
      selectedCount={selection.selectedCount}
      hiddenSelectedCount={selection.hiddenSelectedCount}
      mergeDisabled={mergeDisabled}
      mergeLabel={card.mergeLabel}
      mergingVerb={mergingVerb}
    />
  );

  // The visible box sits next to the Save button that was pressed, or the top one once the bottom one is gone
  // (the page got shorter than BOTTOM_ACTIONS_MIN_ROWS rows).
  const showBottomActions = table.pagedRows.length >= BOTTOM_ACTIONS_MIN_ROWS;
  const statusOrigin: SaveOrigin = save.saveOrigin === 'bottom' && showBottomActions ? 'bottom' : 'top';
  const hasVisibleStatus = Boolean(save.saveProgress || save.saveStatus);
  const statusFor = (origin: SaveOrigin): ReactNode =>
    hasVisibleStatus && statusOrigin === origin ? (
      <div className="search-table-save-status">
        <VisibleSaveStatus
          saveProgress={save.saveProgress}
          saveStatus={save.saveStatus}
          mergingVerb={mergingVerb}
          viewMergedResultsLabel={card.viewMergedResultsLabel}
          onViewMergedResults={card.onViewMergedResults}
        />
      </div>
    ) : null;
  const {onRefresh, resultsMotionKey} = card;

  return (
    <section
      className={`project-grid-card search-table-card${card.className ? ` ${card.className}` : ''}`}
      data-search-table-id={tableId}
      aria-busy={save.isSaving}
    >
      <SearchTableCardHeader card={card} isSaving={save.isSaving} />
      <p className="project-grid-card-copy">{card.description}</p>

      <SaveStatusAnnouncer saveProgress={save.saveProgress} saveStatus={save.saveStatus} mergingVerb={mergingVerb} />

      <div
        key={resultsMotionKey === undefined ? 'search-table-static-results' : `search-table-results-${resultsMotionKey}`}
        className={resultsMotionKey ? 'search-table-results-motion' : undefined}
      >
        <SearchTableGrid
          card={card}
          tableRows={tableRows}
          selection={selection}
          toolbar={
            <SearchTableToolbar
              tableRows={tableRows}
              save={save}
              saveControls={saveControls('top')}
              topStatus={statusFor('top')}
              isPhone={isPhone}
              onRefresh={onRefresh ? () => onRefresh(tableId) : undefined}
            />
          }
        />
        {showBottomActions ? (
          <div className="search-table-bottom-actions" role="group" aria-label={`Save from ${title}`}>
            <div className="project-grid-toolbar-cluster search-table-save-group">{saveControls('bottom')}</div>
            {statusFor('bottom')}
          </div>
        ) : null}
      </div>

      <LargeSaveDialog save={save} mergeVerb={card.mergeVerb} hiddenSelectedCount={selection.hiddenSelectedCount} />
    </section>
  );
}
