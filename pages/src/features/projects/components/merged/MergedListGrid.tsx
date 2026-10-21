import {useId, useState, type ReactNode} from 'react';
import {ProjectGridTable} from '../ProjectGridTable';
import {PAST_PROJECT_GRID_COLUMNS, type ProjectGridItem} from '../projectGrid';
import {pluralize} from '../saveResults';
import type {useProjectGridTable} from '../useProjectGridTable';

interface MergedListGridProps {
  table: ReturnType<typeof useProjectGridTable>;
  rows: ProjectGridItem[];
  sharedMode: boolean;
  highlightedKeys?: ReadonlySet<string>;
  onDeleteRow?: (row: ProjectGridItem) => void;
  deleteDisabled: boolean;
  selectable: boolean;
  toolbar: ReactNode;
}

/** The merged rows' table. On phones the builder's list is collapsed behind a disclosure (see mergedResults.css). */
export const MergedListGrid = ({
  table,
  rows,
  sharedMode,
  highlightedKeys,
  onDeleteRow,
  deleteDisabled,
  selectable,
  toolbar,
}: MergedListGridProps) => {
  const [isPhoneListOpen, setIsPhoneListOpen] = useState(false);
  const phoneListId = useId();

  // Select-all targets the rows currently visible (matching the active search), so a narrowed view +
  // Remove Selected can never delete rows the user cannot see.
  const handleToggleSelectAll = () => {
    const visible = table.filteredRows;
    const allVisibleSelected = visible.length > 0 && visible.every((row) => table.selectedKeys.has(row.__key));
    if (allVisibleSelected) {
      table.clearSelection();
    } else {
      table.selectRows(visible);
    }
  };

  return (
    <>
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
          highlightedKeys={highlightedKeys}
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
          onDeleteRow={onDeleteRow}
          deleteDisabled={deleteDisabled}
          selectable={selectable}
          selectedKeys={table.selectedKeys}
          selectAllStateRows={table.filteredRows}
          onToggleSelected={table.toggleSelected}
          onToggleSelectAll={handleToggleSelectAll}
          toolbarPlacement="bottom"
          toolbar={toolbar}
        />
      </div>
    </>
  );
};

interface NarrowedSearchHintProps {
  shownCount: number;
  totalCount: number;
  /** Rows from the latest save that the search hides. */
  hiddenAddedCount: number;
  onClearSearch: () => void;
}

// In the builder the link and exports take the rows the search shows; say so when it hides some, above
// all when it hides projects that were just saved.
export const NarrowedSearchHint = ({shownCount, totalCount, hiddenAddedCount, onClearSearch}: NarrowedSearchHintProps) => (
  <p className="itg-notice project-grid-narrowed-hint" role={hiddenAddedCount ? 'status' : undefined}>
    {hiddenAddedCount
      ? `${hiddenAddedCount === 1 ? '1 newly saved project is' : `${hiddenAddedCount} newly saved projects are`} hidden by your search.`
      : `Your search shows ${shownCount} of ${totalCount} saved projects.`}{' '}
    Saving and exports include only the {shownCount} it shows.{' '}
    <button type="button" className="itg-btn itg-btn-text past-projects-status-action" onClick={onClearSearch}>
      Clear search
    </button>
  </p>
);
