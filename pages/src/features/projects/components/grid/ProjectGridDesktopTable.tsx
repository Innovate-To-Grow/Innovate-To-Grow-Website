import {
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridLinkScope,
  type ProjectGridSortDirection,
} from '../projectGrid';
import {DesktopRow} from './ProjectGridDesktopRow';

interface ProjectGridDesktopTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  linkScope: ProjectGridLinkScope;
  selectable: boolean;
  selectedKeys: Set<string>;
  selectAllStateRows?: ProjectGridItem[];
  onToggleSelected?: (rowKey: string) => void;
  onToggleSelectAll?: () => void;
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  onSortChange: (field: ProjectGridColumnKey) => void;
  expandedKeys: Set<string>;
  onToggleExpanded: (rowKey: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  deleteDisabled?: boolean;
  loadMissingDetails?: boolean;
  isRowSaved?: (row: ProjectGridItem) => boolean;
  savedRowLabel?: string;
  highlightedKeys?: ReadonlySet<string>;
}

export const ProjectGridDesktopTable = ({
  columns,
  rows,
  pagedRows,
  linkScope,
  selectable,
  selectedKeys,
  selectAllStateRows,
  onToggleSelected,
  onToggleSelectAll,
  sortField,
  sortDirection,
  onSortChange,
  expandedKeys,
  onToggleExpanded,
  onDeleteRow,
  deleteDisabled = false,
  loadMissingDetails,
  isRowSaved,
  savedRowLabel = 'Saved',
  highlightedKeys,
}: ProjectGridDesktopTableProps) => {
  const selectionScopeRows = selectAllStateRows ?? rows;
  const selectedInScopeCount = selectionScopeRows.filter((row) => selectedKeys.has(row.__key)).length;
  const allSelected = selectable && selectionScopeRows.length > 0 && selectedInScopeCount === selectionScopeRows.length;
  const partiallySelected = selectable && selectedInScopeCount > 0 && !allSelected;
  const tableClassName = [
    'itg-table',
    'project-grid-table',
    selectable ? 'is-selectable' : '',
    onDeleteRow ? 'has-remove' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="project-grid-table-wrap">
      <table className={tableClassName}>
        <thead>
          <tr>
            {selectable ? (
              <th scope="col" className="project-grid-select-col">
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

            {columns.map((column) => {
              const isSorted = sortField === column.key;
              // The sort arrows are the header's background (DataTables style); aria-sort states the order.
              const sortClass = isSorted ? ` is-sorted is-sorted-${sortDirection}` : '';
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={`project-grid-col-${column.key} project-grid-sortable${sortClass}`}
                  aria-sort={isSorted ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  <button type="button" className="project-grid-sort-button" onClick={() => onSortChange(column.key)}>
                    {column.label}
                  </button>
                </th>
              );
            })}

            <th scope="col" className="project-grid-actions-col">
              Details{onDeleteRow ? <span className="sr-only"> and removal</span> : null}
            </th>
          </tr>
        </thead>

        <tbody>
          {pagedRows.map((row, index) => (
            <DesktopRow
              key={row.__key}
              row={row}
              isOdd={index % 2 === 0}
              columns={columns}
              linkScope={linkScope}
              selectable={selectable}
              isSelected={selectedKeys.has(row.__key)}
              onToggleSelected={onToggleSelected}
              isExpanded={expandedKeys.has(row.__key)}
              onToggleExpanded={onToggleExpanded}
              onDeleteRow={onDeleteRow}
              deleteDisabled={deleteDisabled}
              loadMissingDetails={loadMissingDetails}
              isSaved={Boolean(isRowSaved?.(row))}
              savedRowLabel={savedRowLabel}
              isHighlighted={Boolean(highlightedKeys?.has(row.__key))}
              sortField={sortField}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};
