import {Fragment} from 'react';
import type {IdentifiedRow} from './rowIdentity';
import type {SheetRow} from './types';
import type {SortField} from './useSheetsTable';

interface SheetsTableRowProps {
  item: IdentifiedRow;
  index: number;
  columns: Array<{key: SortField; label: string}>;
  sortField: SortField;
  isExpanded: boolean;
  onToggle: () => void;
}

const DetailCell = ({row, detailId, colSpan}: {row: SheetRow; detailId: string; colSpan: number}) => (
  <tr className="sdt-detail-row is-expanded">
    <td id={detailId} colSpan={colSpan} className="sdt-detail-cell">
      {row.Abstract ? <p className="sdt-detail-section">{row.Abstract}</p> : null}
      {row['Student Names'] ? (
        <p className="sdt-detail-section">
          <strong>Team members:</strong> {row['Student Names']}
        </p>
      ) : null}
    </td>
  </tr>
);

/** A project row, with an expandable details row (abstract and team members) when it has any. */
export const SheetsTableRow = ({item, index, columns, sortField, isExpanded, onToggle}: SheetsTableRowProps) => {
  const {detailId, row} = item;
  const hasDetails = Boolean(row.Abstract || row['Student Names']);
  return (
    <Fragment>
      <tr
        className={[
          'sdt-row',
          // Striped over the project rows only, so an open row's details do not shift the stripes.
          index % 2 === 0 ? 'is-odd' : '',
          isExpanded ? 'sdt-row-expanded is-expanded' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {columns.map((column) => (
          <td key={column.key} className={`sdt-td${column.key === sortField ? ' is-sorted-col' : ''}`}>
            {row[column.key]}
          </td>
        ))}
        <td className="sdt-td sdt-td-expand">
          {hasDetails ? (
            <button
              type="button"
              className="sdt-expand-button"
              aria-label={`${isExpanded ? 'Hide' : 'Show'} details for ${row['Project Title'] || row.TeamName}`}
              aria-expanded={isExpanded}
              aria-controls={detailId}
              onClick={onToggle}
            >
              <span className="sdt-expand-icon" aria-hidden="true" />
            </button>
          ) : null}
        </td>
      </tr>
      {isExpanded ? <DetailCell row={row} detailId={detailId} colSpan={columns.length + 1} /> : null}
    </Fragment>
  );
};
