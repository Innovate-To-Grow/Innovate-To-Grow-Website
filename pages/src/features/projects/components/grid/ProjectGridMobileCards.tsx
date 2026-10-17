import {useId} from 'react';
import {
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridItem,
} from '../projectGrid';
import {ProjectGridRowDetails} from './ProjectGridRowDetails';
import {ProjectTitleWithChips} from './ProjectTitleWithChips';

interface ProjectGridMobileCardsProps {
  columns: ProjectGridColumn[];
  pagedRows: ProjectGridItem[];
  emptyMessage: string;
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

export const ProjectGridMobileCards = ({
  columns,
  pagedRows,
  emptyMessage,
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
}: ProjectGridMobileCardsProps) => (
  <div className="project-grid-mobile-cards">
    {!pagedRows.length ? <div className="project-grid-empty">{emptyMessage}</div> : null}

    {pagedRows.map((row) => (
      <MobileCard
        key={row.__key}
        row={row}
        columns={columns}
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
  </div>
);

interface MobileCardProps {
  row: ProjectGridItem;
  columns: ProjectGridColumn[];
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

const MobileCard = ({
  row,
  columns,
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
  const cardClassName = [
    'project-grid-mobile-card',
    isExpanded ? 'is-expanded' : '',
    isSelected ? 'is-selected' : '',
    isSaved ? 'is-saved' : '',
    isHighlighted ? 'is-new' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cardClassName}>
      {selectable ? (
        <div className="project-grid-mobile-card-select">
          <input
            type="checkbox"
            aria-label={`Select ${row.project_title}`}
            checked={isSelected}
            onChange={() => onToggleSelected?.(row.__key)}
          />
        </div>
      ) : null}

      <div className="project-grid-mobile-card-fields">
        {columns.map((column) =>
          row[column.key] ? (
            <div key={column.key} className="project-grid-mobile-card-field">
              <span className="project-grid-mobile-card-label">{column.label}</span>
              <span className="project-grid-mobile-card-value">
                {column.key === 'project_title' ? (
                  <ProjectTitleWithChips
                    title={row.project_title}
                    isNew={isHighlighted}
                    isSaved={isSaved}
                    savedRowLabel={savedRowLabel}
                  />
                ) : (
                  row[column.key]
                )}
              </span>
            </div>
          ) : null,
        )}
      </div>

      <div className="project-grid-mobile-card-actions">
        <button
          type="button"
          className="project-grid-detail-button"
          disabled={!hasDetails}
          aria-expanded={hasDetails ? isExpanded : undefined}
          aria-controls={hasDetails ? detailsId : undefined}
          onClick={() => hasDetails && onToggleExpanded(row.__key)}
        >
          {hasDetails ? (isExpanded ? 'Hide Details' : 'View Details') : 'No Details'}
        </button>
        {onDeleteRow ? (
          <button
            type="button"
            className="project-grid-delete-button"
            onClick={() => onDeleteRow(row)}
            disabled={deleteDisabled}
          >
            Remove
          </button>
        ) : null}
      </div>

      {isExpanded ? (
        <div id={detailsId} className="project-grid-mobile-card-details">
          <ProjectGridRowDetails row={row} loadMissingDetails={loadMissingDetails} />
        </div>
      ) : null}
    </div>
  );
};
