import {useId} from 'react';
import {
  getProjectGridTeamCode,
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridItem,
  type ProjectGridLinkScope,
} from '../projectGrid';
import {ProjectGridRowDetails} from './ProjectGridRowDetails';
import {ProjectTitleWithChips} from './ProjectTitleWithChips';

interface ProjectGridMobileCardsProps {
  columns: ProjectGridColumn[];
  pagedRows: ProjectGridItem[];
  linkScope: ProjectGridLinkScope;
  expandedKeys: Set<string>;
  onToggleExpanded: (rowKey: string) => void;
  selectable: boolean;
  selectedKeys: Set<string>;
  onToggleSelected?: (rowKey: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  deleteDisabled?: boolean;
  loadMissingDetails?: boolean;
  isRowSaved?: (row: ProjectGridItem) => boolean;
  savedRowLabel?: string;
  highlightedKeys?: ReadonlySet<string>;
}

/** The phone layout: one list row per project instead of the wide table. */
export const ProjectGridMobileCards = ({
  columns,
  pagedRows,
  linkScope,
  expandedKeys,
  onToggleExpanded,
  selectable,
  selectedKeys,
  onToggleSelected,
  onDeleteRow,
  deleteDisabled = false,
  loadMissingDetails,
  isRowSaved,
  savedRowLabel = 'Saved',
  highlightedKeys,
}: ProjectGridMobileCardsProps) => {
  // Archive tables lead each row with its term; the current-projects list is all one term.
  const showTerm = columns.some((column) => column.key === 'semester_label');

  return (
    <ol className="project-grid-mobile-cards">
      {pagedRows.map((row) => (
        <MobileCard
          key={row.__key}
          row={row}
          showTerm={showTerm}
          linkScope={linkScope}
          isExpanded={expandedKeys.has(row.__key)}
          onToggleExpanded={onToggleExpanded}
          selectable={selectable}
          isSelected={selectedKeys.has(row.__key)}
          onToggleSelected={onToggleSelected}
          onDeleteRow={onDeleteRow}
          deleteDisabled={deleteDisabled}
          loadMissingDetails={loadMissingDetails}
          isSaved={Boolean(isRowSaved?.(row))}
          savedRowLabel={savedRowLabel}
          isHighlighted={Boolean(highlightedKeys?.has(row.__key))}
        />
      ))}
    </ol>
  );
};

interface MobileCardProps {
  row: ProjectGridItem;
  showTerm: boolean;
  linkScope: ProjectGridLinkScope;
  isExpanded: boolean;
  onToggleExpanded: (rowKey: string) => void;
  selectable: boolean;
  isSelected: boolean;
  onToggleSelected?: (rowKey: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  deleteDisabled: boolean;
  loadMissingDetails?: boolean;
  isSaved: boolean;
  savedRowLabel: string;
  isHighlighted: boolean;
}

/** Non-empty parts joined with " · ". */
const joinParts = (parts: (string | null | undefined)[]) =>
  parts
    .map((part) => (part ?? '').trim())
    .filter(Boolean)
    .join(' · ');

const mobileCardClassName = (state: {
  isExpanded: boolean;
  isSelected: boolean;
  isSaved: boolean;
  isHighlighted: boolean;
  selectable: boolean;
}) =>
  [
    'project-grid-mobile-card',
    state.isExpanded ? 'is-expanded' : '',
    state.isSelected ? 'is-selected' : '',
    state.isSaved ? 'is-saved' : '',
    state.isHighlighted ? 'is-new' : '',
    state.selectable ? 'is-selectable' : '',
  ]
    .filter(Boolean)
    .join(' ');

interface MobileCardActionsProps
  extends Pick<MobileCardProps, 'row' | 'isExpanded' | 'onToggleExpanded' | 'onDeleteRow' | 'deleteDisabled'> {
  hasDetails: boolean;
  detailsId: string;
}

/** "Show details" and "Remove" under a card. */
const MobileCardActions = ({
  row,
  hasDetails,
  isExpanded,
  detailsId,
  onToggleExpanded,
  onDeleteRow,
  deleteDisabled,
}: MobileCardActionsProps) => (
  <div className="project-grid-mobile-card-actions">
    {hasDetails ? (
      <button
        type="button"
        className="itg-btn itg-btn-text project-grid-detail-button"
        aria-expanded={isExpanded}
        aria-controls={detailsId}
        onClick={() => onToggleExpanded(row.__key)}
      >
        {isExpanded ? 'Hide details' : 'Show details'}
        <span aria-hidden="true">{isExpanded ? ' ▴' : ' ▾'}</span>
      </button>
    ) : null}
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
  </div>
);

const MobileCard = ({
  row,
  showTerm,
  linkScope,
  isExpanded,
  onToggleExpanded,
  selectable,
  isSelected,
  onToggleSelected,
  onDeleteRow,
  deleteDisabled,
  loadMissingDetails,
  isSaved,
  savedRowLabel,
  isHighlighted,
}: MobileCardProps) => {
  const hasDetails = hasProjectGridDetails(row);
  const detailsId = useId();
  const cardClassName = mobileCardClassName({isExpanded, isSelected, isSaved, isHighlighted, selectable});
  const meta = joinParts([showTerm ? row.semester_label : '', getProjectGridTeamCode(row), row.industry]);
  const byline = joinParts([row.team_name, row.organization]);

  return (
    <li className={cardClassName}>
      {selectable ? (
        <label className="project-grid-mobile-card-select">
          <input
            type="checkbox"
            aria-label={`Select ${row.project_title}`}
            checked={isSelected}
            onChange={() => onToggleSelected?.(row.__key)}
          />
          <span aria-hidden="true">Select</span>
        </label>
      ) : null}

      <div className="project-grid-mobile-card-body">
        {meta ? <p className="project-grid-mobile-card-meta">{meta}</p> : null}
        <ProjectTitleWithChips
          row={row}
          scope={linkScope}
          isNew={isHighlighted}
          isSaved={isSaved}
          savedRowLabel={savedRowLabel}
        />
        {byline ? <p className="project-grid-mobile-card-byline">{byline}</p> : null}

        {isExpanded ? (
          <div id={detailsId} className="project-grid-mobile-card-details">
            <ProjectGridRowDetails row={row} scope={linkScope} loadMissingDetails={loadMissingDetails} />
          </div>
        ) : null}

        {hasDetails || onDeleteRow ? (
          <MobileCardActions
            row={row}
            hasDetails={hasDetails}
            isExpanded={isExpanded}
            detailsId={detailsId}
            onToggleExpanded={onToggleExpanded}
            onDeleteRow={onDeleteRow}
            deleteDisabled={deleteDisabled}
          />
        ) : null}
      </div>
    </li>
  );
};
