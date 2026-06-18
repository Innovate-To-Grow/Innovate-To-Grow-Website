import {useCallback, useState, type ReactNode} from 'react';
import {ProjectGridTable} from './ProjectGridTable';
import {useProjectGridTable} from './useProjectGridTable';
import {
  PAST_PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

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
  onRemove: (tableId: string) => void;
  onRefresh?: (tableId: string) => void;
  /** Push this table's checked rows into the shared/merged results. */
  onMergeSelected: (rows: ProjectGridRow[]) => void;
}

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
  description = 'Filter this table, select rows to save, delete, or keep, then save the rest into your results.',
  emptyMessage = 'No rows available in this search table.',
  initialRows,
  resultsMotionKey,
  searchControl,
  controlsStatus,
  tableId,
  title,
  mergeLabel = 'Save Selected',
  onRemove,
  onRefresh,
  onMergeSelected,
}: SearchTableCardProps) {
  const [rows, setRows] = useState<ProjectGridItem[]>(() => createProjectGridItems(initialRows, tableId));
  const [undoRows, setUndoRows] = useState<ProjectGridItem[] | null>(null);
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
  });

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

  const handleKeepSelectedRows = useCallback(() => {
    if (!table.hasSelection) {
      return;
    }

    const nextRows = table.keepSelectedRows(rows);
    if (nextRows.length === rows.length) {
      table.clearSelection();
      return;
    }

    setUndoRows(rows);
    setRows(nextRows);
    table.clearSelection();
  }, [rows, table]);

  const handleSaveSelectedRows = useCallback(() => {
    if (!table.hasSelection) {
      return;
    }

    onMergeSelected(table.selectedRows.map(stripProjectGridItem));
    table.clearSelection();
  }, [onMergeSelected, table]);

  const handleUndoLastRowAction = useCallback(() => {
    if (!undoRows) {
      return;
    }

    setRows(undoRows);
    setUndoRows(null);
    table.clearSelection();
  }, [table, undoRows]);

  return (
    <section className={`project-grid-card search-table-card${className ? ` ${className}` : ''}`}>
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
          >
            <SearchTableRemoveIcon />
          </button>
        ) : null}
      </div>

      <div
        key={resultsMotionKey === undefined ? 'search-table-static-results' : `search-table-results-${resultsMotionKey}`}
        className={resultsMotionKey ? 'search-table-results-motion' : undefined}
      >
        <ProjectGridTable
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
              <button
                type="button"
                className="itg-btn itg-btn-primary"
                onClick={handleSaveSelectedRows}
                disabled={!table.hasSelection}
              >
                {mergeLabel}
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={handleDeleteSelectedRows}
                disabled={!table.hasSelection}
              >
                Delete Selected
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={handleKeepSelectedRows}
                disabled={!table.hasSelection}
              >
                Keep Selected
              </button>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={handleUndoLastRowAction}
                disabled={!undoRows}
              >
                Undo Row Change
              </button>
              <button type="button" className="itg-btn itg-btn-outline" onClick={table.selectAllRows}>
                Select All Entries
              </button>
              <button type="button" className="itg-btn itg-btn-outline" onClick={table.clearSelection}>
                Deselect
              </button>
              {onRefresh ? (
                <button type="button" className="itg-btn itg-btn-outline" onClick={() => onRefresh(tableId)}>
                  Refresh Search Table
                </button>
              ) : null}
            </div>
          }
        />
      </div>
    </section>
  );
}
