import type {ReactNode} from 'react';
import {
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from './projectGrid';
import {ProjectGridDesktopTable} from './grid/ProjectGridDesktopTable';
import {ProjectGridMobileCards} from './grid/ProjectGridMobileCards';
import './ProjectsTables.css';

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
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
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
  page,
  totalPages,
  onPageChange,
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
    <div className="project-grid-table-shell">
      {toolbar ? <div className="project-grid-toolbar">{toolbar}</div> : null}

      <div className="project-grid-controls">
        <label className="project-grid-search">
          <span className="project-grid-search-label">Search</span>
          <input
            type="text"
            value={search}
            placeholder={searchPlaceholder}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>

        <div className="project-grid-count">
          {filteredCount} of {totalCount} {countLabel}
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
