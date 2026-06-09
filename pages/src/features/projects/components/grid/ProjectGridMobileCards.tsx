import {
  hasProjectGridDetails,
  type ProjectGridColumn,
  type ProjectGridItem,
} from '../projectGrid';

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
}: MobileCardProps) => {
  const hasDetails = hasProjectGridDetails(row);

  return (
    <div className={`project-grid-mobile-card${isExpanded ? ' is-expanded' : ''}${isSelected ? ' is-selected' : ''}`}>
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
              <span className="project-grid-mobile-card-value">{row[column.key]}</span>
            </div>
          ) : null,
        )}
      </div>

      <div className="project-grid-mobile-card-actions">
        <button type="button" className="project-grid-detail-button" disabled={!hasDetails} onClick={() => hasDetails && onToggleExpanded(row.__key)}>
          {hasDetails ? (isExpanded ? 'Hide Details' : 'View Details') : 'No Details'}
        </button>
        {onDeleteRow ? <button type="button" className="project-grid-delete-button" onClick={() => onDeleteRow(row)}>Remove</button> : null}
      </div>

      {isExpanded ? (
        <div className="project-grid-mobile-card-details">
          {row.abstract ? <div><strong>Abstract:</strong> {row.abstract}</div> : null}
          {row.student_names ? <div><strong>Student Names:</strong> {row.student_names}</div> : null}
        </div>
      ) : null}
    </div>
  );
};
