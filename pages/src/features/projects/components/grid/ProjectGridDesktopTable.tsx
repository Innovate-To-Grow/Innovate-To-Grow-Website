import {useId} from 'react';
import {
  getProjectGridTeamCode,
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridLinkScope,
  type ProjectGridSortDirection,
} from '../projectGrid';
import {ProjectGridRowDetails} from './ProjectGridRowDetails';
import {ProjectTitleWithChips} from './ProjectTitleWithChips';

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

interface DesktopRowProps {
  row: ProjectGridItem;
  /** Striped like DataTables' "odd" rows: counted over the project rows, not the detail rows between them. */
  isOdd: boolean;
  columns: ProjectGridColumn[];
  linkScope: ProjectGridLinkScope;
  selectable: boolean;
  isSelected: boolean;
  onToggleSelected?: (rowKey: string) => void;
  isExpanded: boolean;
  onToggleExpanded: (rowKey: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  deleteDisabled: boolean;
  loadMissingDetails?: boolean;
  isSaved: boolean;
  savedRowLabel: string;
  isHighlighted: boolean;
  sortField: ProjectGridColumnKey;
}

const DesktopRow = ({
  row,
  isOdd,
  columns,
  linkScope,
  selectable,
  isSelected,
  onToggleSelected,
  isExpanded,
  onToggleExpanded,
  onDeleteRow,
  deleteDisabled,
  loadMissingDetails,
  isSaved,
  savedRowLabel,
  isHighlighted,
  sortField,
}: DesktopRowProps) => {
  const hasDetails = hasProjectGridDetails(row);
  const detailsId = useId();
  const rowClassName = [
    'project-grid-row',
    isOdd ? 'is-odd' : '',
    isSelected ? 'is-selected' : '',
    isExpanded ? 'is-expanded' : '',
    isSaved ? 'is-saved' : '',
    isHighlighted ? 'is-new' : '',
  ]
    .filter(Boolean)
    .join(' ');
  // The expanded details sit under every column except the leading one (and the checkbox), like the drafts.
  const leadingColumns = Number(selectable) + 1;
  const detailColumns = columns.length + Number(selectable) + 1 - leadingColumns;

  const renderCell = (key: ProjectGridColumnKey) => {
    switch (key) {
      case 'semester_label':
        return (
          <>
            <span className="project-grid-term">{row.semester_label}</span>
            <span className="project-grid-team-code">{getProjectGridTeamCode(row)}</span>
          </>
        );
      case 'class_code':
        return <span className="project-grid-team-code">{getProjectGridTeamCode(row)}</span>;
      case 'project_title':
        return (
          <>
            <ProjectTitleWithChips
              row={row}
              scope={linkScope}
              isNew={isHighlighted}
              isSaved={isSaved}
              savedRowLabel={savedRowLabel}
            />
            {row.team_name ? <span className="project-grid-team-name">{row.team_name}</span> : null}
          </>
        );
      default:
        return row[key];
    }
  };

  return (
    <>
      <tr className={rowClassName}>
        {selectable ? (
          <td className="project-grid-select-col">
            <input
              type="checkbox"
              aria-label={`Select ${row.project_title}`}
              checked={isSelected}
              onChange={() => onToggleSelected?.(row.__key)}
            />
          </td>
        ) : null}

        {columns.map((column) => (
          <td
            key={column.key}
            className={`project-grid-col-${column.key}${column.key === sortField ? ' is-sorted-col' : ''}`}
          >
            {renderCell(column.key)}
          </td>
        ))}

        <td className="project-grid-actions-col">
          {hasDetails ? (
            <button
              type="button"
              className="project-grid-detail-button project-grid-detail-icon-button"
              aria-expanded={isExpanded}
              aria-controls={detailsId}
              onClick={() => onToggleExpanded(row.__key)}
            >
              {/* The reference's navy square with a white arrow; the hidden text names the button. */}
              <span className="project-grid-detail-icon" aria-hidden="true" />
              <span className="sr-only">{isExpanded ? 'Hide' : 'Details'}</span>
            </button>
          ) : (
            <span className="project-grid-no-details">No details</span>
          )}
          {onDeleteRow ? (
            <button
              type="button"
              className="itg-btn itg-btn-text itg-btn-danger project-grid-delete-button"
              onClick={() => onDeleteRow(row)}
              disabled={deleteDisabled}
            >
              Remove
            </button>
          ) : null}
        </td>
      </tr>

      {isExpanded ? (
        <tr className="project-grid-detail-row is-expanded">
          <td className="project-grid-detail-spacer" colSpan={leadingColumns} />
          <td colSpan={detailColumns}>
            <div id={detailsId} className="project-grid-detail-content">
              <ProjectGridRowDetails row={row} scope={linkScope} loadMissingDetails={loadMissingDetails} />
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
};
