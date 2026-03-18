import type {ReactNode} from 'react';
import {
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from './projectGrid';
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

const detailColspan = (
  baseColumns: number,
  selectable: boolean,
  hasDelete: boolean,
) => baseColumns + 1 + (selectable ? 1 : 0) + (hasDelete ? 1 : 0);

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
  const allSelected = selectable && rows.length > 0 && selectedKeys.size === rows.length;
  const partiallySelected = selectable && selectedKeys.size > 0 && selectedKeys.size < rows.length;

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
          <div className="project-grid-table-wrap">
            <table className="project-grid-table">
              <thead>
                <tr>
                  {selectable ? (
                    <th className="project-grid-select-col">
                      <input
                        type="checkbox"
                        aria-label="Select all rows"
                        checked={allSelected}
                        ref={(input) => {
                          if (input) {
                            input.indeterminate = partiallySelected;
                          }
                        }}
                        onChange={onToggleSelectAll}
                      />
                    </th>
                  ) : null}

                  {columns.map((column) => (
                    <th key={column.key}>
                      <button type="button" onClick={() => onSortChange(column.key)}>
                        <span>{column.label}</span>
                        {sortField === column.key ? (
                          <span className="project-grid-sort-indicator">
                            {sortDirection === 'asc' ? '▲' : '▼'}
                          </span>
                        ) : null}
                      </button>
                    </th>
                  ))}

                  <th className="project-grid-detail-col">Details</th>
                  {onDeleteRow ? <th className="project-grid-delete-col">Remove</th> : null}
                </tr>
              </thead>

              <tbody>
                {!pagedRows.length ? (
                  <tr>
                    <td colSpan={detailColspan(columns.length, selectable, Boolean(onDeleteRow))}>
                      <div className="project-grid-empty">{emptyMessage}</div>
                    </td>
                  </tr>
                ) : null}

                {pagedRows.map((row) => {
                  const isExpanded = expandedKeys.has(row.__key);
                  const isSelected = selectedKeys.has(row.__key);
                  const hasDetails = hasProjectGridDetails(row);

                  return (
                    <FragmentRow
                      key={row.__key}
                      row={row}
                      columns={columns}
                      selectable={selectable}
                      isSelected={isSelected}
                      onToggleSelected={onToggleSelected}
                      isExpanded={isExpanded}
                      onToggleExpanded={onToggleExpanded}
                      hasDetails={hasDetails}
                      onDeleteRow={onDeleteRow}
                      colSpan={detailColspan(columns.length, selectable, Boolean(onDeleteRow))}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>

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

interface FragmentRowProps {
  row: ProjectGridItem;
  columns: ProjectGridColumn[];
  selectable: boolean;
  isSelected: boolean;
  onToggleSelected?: (rowKey: string) => void;
  isExpanded: boolean;
  onToggleExpanded: (rowKey: string) => void;
  hasDetails: boolean;
  onDeleteRow?: (row: ProjectGridItem) => void;
  colSpan: number;
}

const FragmentRow = ({
  row,
  columns,
  selectable,
  isSelected,
  onToggleSelected,
  isExpanded,
  onToggleExpanded,
  hasDetails,
  onDeleteRow,
  colSpan,
}: FragmentRowProps) => (
  <>
    <tr
      className={`project-grid-row${isSelected ? ' is-selected' : ''}${isExpanded ? ' is-expanded' : ''}`}
      onClick={selectable && onToggleSelected ? () => onToggleSelected(row.__key) : undefined}
    >
      {selectable ? (
        <td className="project-grid-select-col">
          <input
            type="checkbox"
            aria-label={`Select ${row.project_title}`}
            checked={isSelected}
            onChange={() => onToggleSelected?.(row.__key)}
            onClick={(event) => event.stopPropagation()}
          />
        </td>
      ) : null}

      {columns.map((column) => (
        <td key={column.key}>{row[column.key]}</td>
      ))}

      <td className="project-grid-detail-col">
        <button
          type="button"
          className="project-grid-detail-button"
          disabled={!hasDetails}
          onClick={(event) => {
            event.stopPropagation();
            if (hasDetails) {
              onToggleExpanded(row.__key);
            }
          }}
        >
          {hasDetails ? (isExpanded ? 'Hide' : 'View') : 'N/A'}
        </button>
      </td>

      {onDeleteRow ? (
        <td className="project-grid-delete-col">
          <button
            type="button"
            className="project-grid-delete-button"
            onClick={(event) => {
              event.stopPropagation();
              onDeleteRow(row);
            }}
          >
            Remove
          </button>
        </td>
      ) : null}
    </tr>

    {isExpanded ? (
      <tr className="project-grid-detail-row">
        <td colSpan={colSpan}>
          <div className="project-grid-detail-content">
            {row.abstract ? (
              <div>
                <strong>Abstract:</strong> {row.abstract}
              </div>
            ) : null}
            {row.student_names ? (
              <div>
                <strong>Student Names:</strong> {row.student_names}
              </div>
            ) : null}
          </div>
        </td>
      </tr>
    ) : null}
  </>
);
