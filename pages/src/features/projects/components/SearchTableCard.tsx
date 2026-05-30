import {forwardRef, useEffect, useImperativeHandle, useState} from 'react';
import {ProjectGridTable} from './ProjectGridTable';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

export interface SearchTableHandle {
  clearSelection: () => void;
  deleteSelectedRows: () => void;
  getFilteredRows: () => ProjectGridRow[];
  hasSelection: () => boolean;
  keepSelectedRows: () => void;
}

interface SearchTableCardProps {
  deleteMode: boolean;
  initialRows: ProjectGridRow[];
  tableId: string;
  title: string;
  onRemove: (tableId: string) => void;
  onSelectionStateChange: (tableId: string, hasSelection: boolean) => void;
}

export const SearchTableCard = forwardRef<SearchTableHandle, SearchTableCardProps>(function SearchTableCard(
  {deleteMode, initialRows, tableId, title, onRemove, onSelectionStateChange},
  ref,
) {
  const [rows, setRows] = useState<ProjectGridItem[]>(() => createProjectGridItems(initialRows, tableId));
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
  });

  useEffect(() => {
    onSelectionStateChange(tableId, table.hasSelection);
  }, [onSelectionStateChange, table.hasSelection, tableId]);

  useImperativeHandle(
    ref,
    () => ({
      clearSelection: table.clearSelection,
      deleteSelectedRows: () => {
        setRows((current) => table.removeSelectedRows(current));
        table.clearSelection();
      },
      getFilteredRows: () => table.sortedRows.map(stripProjectGridItem),
      hasSelection: () => table.hasSelection,
      keepSelectedRows: () => {
        setRows((current) => table.keepSelectedRows(current));
        table.clearSelection();
      },
    }),
    [table],
  );

  return (
    <section className={`project-grid-card search-table-card${deleteMode ? ' is-delete-mode' : ''}`}>
      {deleteMode ? (
        <button
          type="button"
          className="search-table-delete-overlay"
          onClick={() => onRemove(tableId)}
        >
          Delete {title}
        </button>
      ) : null}

      <div className="project-grid-card-header">
        <div>
          <h3 className="project-grid-card-title">{title}</h3>
          <p className="project-grid-card-copy">
            Filter this table, select rows to keep or delete, then merge the remaining results.
          </p>
        </div>
      </div>

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
        emptyMessage="No rows available in this search table."
        countLabel="entries"
        selectable
        selectedKeys={table.selectedKeys}
        onToggleSelected={table.toggleSelected}
        onToggleSelectAll={() => {
          if (table.selectedKeys.size === rows.length && rows.length > 0) {
            table.clearSelection();
          } else {
            table.selectAllRows();
          }
        }}
        toolbar={
          <div className="project-grid-inline-actions">
            <button type="button" className="itg-btn itg-btn-outline" onClick={table.selectAllRows}>
              Select All Entries
            </button>
            <button type="button" className="itg-btn itg-btn-outline" onClick={table.clearSelection}>
              Deselect
            </button>
          </div>
        }
      />
    </section>
  );
});
