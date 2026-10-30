import {useId} from 'react';
import {
  getProjectGridTeamCode,
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridLinkScope,
} from '../contracts/projectGrid';
import {ProjectGridRowDetails} from './ProjectGridRowDetails';
import {ProjectTitleWithChips} from './ProjectTitleWithChips';

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
  /** The row's details say they are loading; false when every row was opened at once (useDetailsAnnouncements). */
  announceDetails: boolean;
}

type DesktopCellProps = Pick<DesktopRowProps, 'row' | 'linkScope' | 'isHighlighted' | 'isSaved' | 'savedRowLabel'> & {
  columnKey: ProjectGridColumnKey;
};

/** One column's cell: the term and team code, the title with its chips and team, or the plain value. */
const DesktopCell = ({columnKey, row, linkScope, isHighlighted, isSaved, savedRowLabel}: DesktopCellProps) => {
  switch (columnKey) {
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
      return row[columnKey];
  }
};

type DesktopActionsCellProps = Pick<
  DesktopRowProps,
  'row' | 'isExpanded' | 'onToggleExpanded' | 'onDeleteRow' | 'deleteDisabled'
> & {hasDetails: boolean; detailsId: string};

/** The details toggle (or "No details") and the Remove button. */
const DesktopActionsCell = ({
  row,
  hasDetails,
  isExpanded,
  detailsId,
  onToggleExpanded,
  onDeleteRow,
  deleteDisabled,
}: DesktopActionsCellProps) => (
  <td className="project-grid-actions-col">
    {hasDetails ? (
      <button
        type="button"
        className="project-grid-detail-button project-grid-detail-icon-button"
        aria-expanded={isExpanded}
        aria-controls={detailsId}
        onClick={() => onToggleExpanded(row.__key)}
      >
        {/* The reference's navy square with a white arrow. The hidden text names the button after its project, one
            name whether open or closed: aria-expanded says which. */}
        <span className="project-grid-detail-icon" aria-hidden="true" />
        <span className="sr-only">{`Details for ${row.project_title}`}</span>
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
);

/** One project row and, when expanded, its details row. */
export const DesktopRow = ({
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
  announceDetails,
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
            <DesktopCell
              columnKey={column.key}
              row={row}
              linkScope={linkScope}
              isHighlighted={isHighlighted}
              isSaved={isSaved}
              savedRowLabel={savedRowLabel}
            />
          </td>
        ))}

        <DesktopActionsCell
          row={row}
          hasDetails={hasDetails}
          isExpanded={isExpanded}
          detailsId={detailsId}
          onToggleExpanded={onToggleExpanded}
          onDeleteRow={onDeleteRow}
          deleteDisabled={deleteDisabled}
        />
      </tr>

      {isExpanded ? (
        <tr className="project-grid-detail-row is-expanded">
          <td className="project-grid-detail-spacer" colSpan={leadingColumns} />
          <td colSpan={detailColumns}>
            {/* A row of its own, away from the title: the group's name says which project these details are of. */}
            <div
              id={detailsId}
              className="project-grid-detail-content"
              role="group"
              aria-label={`Details for ${row.project_title}`}
            >
              <ProjectGridRowDetails
                row={row}
                scope={linkScope}
                loadMissingDetails={loadMissingDetails}
                announce={announceDetails}
              />
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
};
