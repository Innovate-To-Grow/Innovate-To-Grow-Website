import {useId} from 'react';
import {hasProjectGridDetails} from '../contracts/projectGrid';
import {ProjectGridRowDetails} from './ProjectGridRowDetails';
import {DesktopActionsCell, DesktopCell, type DesktopRowProps} from './DesktopRowCells';

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
          <td key={column.key} className={`project-grid-col-${column.key}`}>
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
