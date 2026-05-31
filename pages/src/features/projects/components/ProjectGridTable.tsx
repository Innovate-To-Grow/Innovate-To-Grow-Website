import type {ReactNode} from 'react';
import {
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from './projectGrid';
import {ProjectGridDesktopTable} from './grid/ProjectGridDesktopTable';
import {ProjectGridMobileCards} from './grid/ProjectGridMobileCards';

interface ProjectGridTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  filteredCount: number;
  totalCount: number;
  search: string;
  searchPlaceholder?: string;
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  onSearchChange: (value: string) => void;
  onSortChange: (field: ProjectGridColumnKey) => void;
  expandedKeys: Set<string>;
  onToggleExpanded: (rowKey: string) => void;
  onToggleAllDetails?: () => void;
  allDetailsExpanded?: boolean;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  pageSize: number;
  pageSizeOptions: number[];
  onPageSizeChange: (size: number) => void;
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  countLabel?: string;
  toolbar?: ReactNode;
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onToggleSelected?: (rowKey: string) => void;
  onToggleSelectAll?: () => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

export const ProjectGridTable = ({
  columns,
  rows,
  pagedRows,
  filteredCount,
  totalCount,
  search,
  searchPlaceholder = 'Search projects...',
  sortField,
  sortDirection,
  onSearchChange,
  onSortChange,
  expandedKeys,
  onToggleExpanded,
  onToggleAllDetails,
  allDetailsExpanded = false,
  page,
  totalPages,
  onPageChange,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  loading,
  error,
  emptyMessage = 'No projects found.',
  countLabel = 'projects',
  toolbar,
  selectable = false,
  selectedKeys = new Set<string>(),
  onToggleSelected,
  onToggleSelectAll,
  onDeleteRow,
}: ProjectGridTableProps) => {
  return (
    <div className="project-grid-table-shell" style={{padding: 0}}>
      {toolbar ? <div className="project-grid-toolbar">{toolbar}</div> : null}

      <div className="project-grid-controls">
        <div className="project-grid-controls-inner">
          <span className="project-grid-field-label" id="project-grid-search-label">
            Search
          </span>
          <div className="project-grid-controls-row">
            <input
              id="project-grid-search-input"
              type="search"
              className="project-grid-search-input"
              value={search}
              placeholder={searchPlaceholder}
              aria-labelledby="project-grid-search-label"
              onChange={(event) => onSearchChange(event.target.value)}
            />
            <div className="project-grid-controls-meta" role="group" aria-label="Results and pagination">
              <p className="project-grid-count">
                <span className="project-grid-count-value">
                  {filteredCount} of {totalCount}
                </span>{' '}
                <span className="project-grid-count-label">{countLabel}</span>
              </p>
              <label className="project-grid-page-size">
                <span className="project-grid-field-label">Per page</span>
                <select
                  value={pageSize}
                  aria-label="Rows per page"
                  onChange={(event) => onPageSizeChange(Number(event.target.value))}
                >
                  {pageSizeOptions.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              {onToggleAllDetails ? (
                <button
                  type="button"
                  className="itg-btn itg-btn-outline project-grid-toggle-details"
                  onClick={onToggleAllDetails}
                >
                  {allDetailsExpanded ? 'Hide All Details' : 'Show All Details'}
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {loading ? <div className="project-grid-state">Loading project data...</div> : null}
      {error ? <div className="project-grid-state project-grid-state-error">{error}</div> : null}

      {!loading && !error ? (
        <>
          <ProjectGridDesktopTable
            columns={columns}
            rows={rows}
            pagedRows={pagedRows}
            emptyMessage={emptyMessage}
            selectable={selectable}
            selectedKeys={selectedKeys}
            onToggleSelected={onToggleSelected}
            onToggleSelectAll={onToggleSelectAll}
            sortField={sortField}
            sortDirection={sortDirection}
            onSortChange={onSortChange}
            expandedKeys={expandedKeys}
            onToggleExpanded={onToggleExpanded}
            onDeleteRow={onDeleteRow}
          />

          <ProjectGridMobileCards
            columns={columns}
            pagedRows={pagedRows}
            emptyMessage={emptyMessage}
            expandedKeys={expandedKeys}
            onToggleExpanded={onToggleExpanded}
            selectable={selectable}
            selectedKeys={selectedKeys}
            onToggleSelected={onToggleSelected}
            onDeleteRow={onDeleteRow}
          />

          {totalPages > 1 ? (
            <div className="project-grid-pagination">
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => onPageChange(page - 1)}
                disabled={page === 0}
              >
                Previous
              </button>
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => onPageChange(page + 1)}
                disabled={page >= totalPages - 1}
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
};
