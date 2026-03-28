import {
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from '../projectGrid';

interface ProjectGridDesktopTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  emptyMessage: string;
  selectable: boolean;
  selectedKeys: Set<string>;
  onToggleSelected?: (rowKey: string) => void;
  onToggleSelectAll?: () => void;
  sortField: ProjectGridColumn['key'];
  sortDirection: ProjectGridSortDirection;
  onSortChange: (field: ProjectGridColumn['key']) => void;
  expandedKeys: Set<string>;
  onToggleExpanded: (rowKey: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

const detailColspan = (baseColumns: number, selectable: boolean, hasDelete: boolean) =>
  baseColumns + 1 + Number(selectable) + Number(hasDelete);

export const ProjectGridDesktopTable = ({
  columns,
  rows, pagedRows, emptyMessage, selectable, selectedKeys, onToggleSelected, onToggleSelectAll,
  sortField, sortDirection, onSortChange, expandedKeys, onToggleExpanded, onDeleteRow,
}: ProjectGridDesktopTableProps) => {
  const allSelected = selectable && rows.length > 0 && selectedKeys.size === rows.length;
  const partiallySelected = selectable && selectedKeys.size > 0 && selectedKeys.size < rows.length;
  const colSpan = detailColspan(columns.length, selectable, Boolean(onDeleteRow));

  return (
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
                    if (input) input.indeterminate = partiallySelected;
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
                    <span className="project-grid-sort-indicator">{sortDirection === 'asc' ? '▲' : '▼'}</span>
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
              <td colSpan={colSpan}>
                <div className="project-grid-empty">{emptyMessage}</div>
              </td>
            </tr>
          ) : null}

          {pagedRows.map((row) => (
            <DesktopRow
              key={row.__key}
              row={row}
              columns={columns}
              selectable={selectable}
              isSelected={selectedKeys.has(row.__key)}
              onToggleSelected={onToggleSelected}
              isExpanded={expandedKeys.has(row.__key)}
              onToggleExpanded={onToggleExpanded}
              onDeleteRow={onDeleteRow}
              colSpan={colSpan}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

interface DesktopRowProps {
  row: ProjectGridItem;
  columns: ProjectGridColumn[];
  selectable: boolean;
  isSelected: boolean;
  onToggleSelected?: (rowKey: string) => void;
  isExpanded: boolean;
  onToggleExpanded: (rowKey: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  colSpan: number;
}

const DesktopRow = ({
  row,
  columns,
  selectable,
  isSelected,
  onToggleSelected,
  isExpanded,
  onToggleExpanded,
  onDeleteRow,
  colSpan,
}: DesktopRowProps) => {
  const hasDetails = hasProjectGridDetails(row);

  return (
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
              if (hasDetails) onToggleExpanded(row.__key);
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
              {row.abstract ? <div><strong>Abstract:</strong> {row.abstract}</div> : null}
              {row.student_names ? <div><strong>Student Names:</strong> {row.student_names}</div> : null}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
};
