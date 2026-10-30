import {
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridLinkScope,
  type ProjectGridSortDirection,
} from '../contracts/projectGrid';
import {DesktopRow} from './ProjectGridDesktopRow';

interface ProjectGridDesktopTableProps {
  /** The table's accessible name (ProjectGridTableProps.tableLabel). */
  tableLabel?: string;
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
  announceDetails: boolean;
}

type DesktopTableHeadProps = Pick<
  ProjectGridDesktopTableProps,
  | 'columns'
  | 'rows'
  | 'selectable'
  | 'selectedKeys'
  | 'selectAllStateRows'
  | 'onToggleSelectAll'
  | 'sortField'
  | 'sortDirection'
  | 'onSortChange'
> & {hasRemove: boolean};

/** The header row: "select all" (when rows can be checked), a sort button per column, and the Details heading. */
const DesktopTableHead = ({
  columns,
  rows,
  selectable,
  selectedKeys,
  selectAllStateRows,
  onToggleSelectAll,
  sortField,
  sortDirection,
  onSortChange,
  hasRemove,
}: DesktopTableHeadProps) => {
  const selectionScopeRows = selectAllStateRows ?? rows;
  const selectedInScopeCount = selectionScopeRows.filter((row) => selectedKeys.has(row.__key)).length;
  const allSelected = selectable && selectionScopeRows.length > 0 && selectedInScopeCount === selectionScopeRows.length;
  const partiallySelected = selectable && selectedInScopeCount > 0 && !allSelected;

  return (
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
          // The sort arrows are drawn after the button (DataTables style); aria-sort states the order.
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
          {/* The space is its own text node: a hidden span's leading space is dropped from the heading's name. */}
          Details
          {hasRemove ? (
            <>
              {' '}
              <span className="sr-only">and removal</span>
            </>
          ) : null}
        </th>
      </tr>
    </thead>
  );
};

export const ProjectGridDesktopTable = ({
  tableLabel,
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
  announceDetails,
}: ProjectGridDesktopTableProps) => {
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
      <table className={tableClassName} aria-label={tableLabel}>
        <DesktopTableHead
          columns={columns}
          rows={rows}
          selectable={selectable}
          selectedKeys={selectedKeys}
          selectAllStateRows={selectAllStateRows}
          onToggleSelectAll={onToggleSelectAll}
          sortField={sortField}
          sortDirection={sortDirection}
          onSortChange={onSortChange}
          hasRemove={Boolean(onDeleteRow)}
        />

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
              announceDetails={announceDetails}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};
