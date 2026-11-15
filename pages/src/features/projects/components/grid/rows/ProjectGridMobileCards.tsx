import {
  type ProjectGridColumn,
  type ProjectGridItem,
  type ProjectGridLinkScope,
} from '../contracts/projectGrid';
import {MobileCard} from './MobileCard';

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
  announceDetails: boolean;
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
  announceDetails,
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
          announceDetails={announceDetails}
        />
      ))}
    </ol>
  );
};
