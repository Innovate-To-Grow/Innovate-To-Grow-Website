import {type ReactNode} from 'react';
import {ProjectGridTable} from '../../grid/table/ProjectGridTable';
import {PastProjectsDialog} from '../../curation/builder/dialog/PastProjectsDialog';
import {PAST_PROJECT_GRID_COLUMNS} from '../../grid/contracts/projectGrid';
import {pluralize} from '../../shared/utils/saveResults';
import {useSearchTableRows} from '../state/useSearchTableRows';
import {useSearchTableSave} from '../state/useSearchTableSave';
import {useSearchTableSelection} from '../state/useSearchTableSelection';
import {type CardProps} from './searchTableCardProps';

type TableRows = ReturnType<typeof useSearchTableRows>;
type Save = ReturnType<typeof useSearchTableSave>;
type Selection = ReturnType<typeof useSearchTableSelection>;

export const SearchTableCardHeader = ({card, headingId, isSaving}: {card: CardProps; headingId: string; isSaving: boolean}) => (
  <div className="project-grid-card-header search-table-card-header">
    {/* Focusable from script: deleting the table next to this one moves focus here. */}
    <h3 id={headingId} className="project-grid-card-title" tabIndex={-1}>
      {card.title}
    </h3>
    {card.canRemove ? (
      <button
        type="button"
        className="itg-btn itg-btn-text search-table-remove-button"
        aria-label={`Delete Table: ${card.title}`}
        onClick={() => card.onRemove(card.tableId)}
        disabled={isSaving}
      >
        Delete Table
      </button>
    ) : null}
  </div>
);

/**
 * How many rows are checked, for screen readers. Select All and the header checkbox check every row the search
 * matches, on every page, so a few visible rows can mean hundreds checked. A polite live region like the table's
 * count line; the card's status is its save outcome.
 */
export const SelectionAnnouncer = ({selectedCount, hiddenSelectedCount}: {selectedCount: number; hiddenSelectedCount: number}) => (
  <p className="sr-only" aria-live="polite">
    {selectedCount
      ? `${pluralize(selectedCount, 'project')} selected` +
        (hiddenSelectedCount ? `, ${hiddenSelectedCount} of them not shown by the current search` : '')
      : ''}
  </p>
);

/** Confirms saving a large selection, whose details all have to be loaded first. */
export const LargeSaveDialog = ({save, mergeVerb, hiddenSelectedCount}: {save: Save; mergeVerb: string; hiddenSelectedCount: number}) =>
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

export const SearchTableGrid = ({card, tableRows, selection, toolbar}: SearchTableGridProps) => {
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
      tableLabel={card.title}
      search={table.search}
      serverSearch={table.serverSearch}
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
