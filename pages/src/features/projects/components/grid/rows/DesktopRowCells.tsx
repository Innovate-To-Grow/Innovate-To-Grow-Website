import {
  getProjectGridTeamCode,
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridLinkScope,
} from '../contracts/projectGrid';
import {ProjectTitleWithChips} from './ProjectTitleWithChips';

export interface DesktopRowProps {
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
  /** The row's details say they are loading; false when every row was opened at once (useDetailsAnnouncements). */
  announceDetails: boolean;
}

type DesktopCellProps = Pick<DesktopRowProps, 'row' | 'linkScope' | 'isHighlighted' | 'isSaved' | 'savedRowLabel'> & {
  columnKey: ProjectGridColumnKey;
};

/** One column's cell: the term and team code, the title with its chips and team, or the plain value. */
export const DesktopCell = ({columnKey, row, linkScope, isHighlighted, isSaved, savedRowLabel}: DesktopCellProps) => {
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
export const DesktopActionsCell = ({
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
        {/* A square outline button with an arrow. The hidden text names the button after its project, one name
            whether open or closed: aria-expanded says which. */}
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
        // Named after its project, so one row's Remove is told from the next in a list of buttons.
        aria-label={`Remove ${row.project_title}`}
        onClick={() => onDeleteRow(row)}
        disabled={deleteDisabled}
      >
        Remove
      </button>
    ) : null}
  </td>
);
