import {useSearchParams} from 'react-router';
import {SheetsTableRow} from './SheetsTableRow';
import type {SheetRow} from './types';
import {useSheetsTable, type SortField} from './useSheetsTable';
import './SheetsDataTable.css';

interface ColumnDef {
  key: SortField;
  label: string;
}

interface SheetsDataTableProps {
  rows: SheetRow[];
  loading?: boolean;
  error?: string | null;
  columns?: ColumnDef[];
  initialSearch?: string;
}

const DEFAULT_COLUMNS: ColumnDef[] = [
  {key: 'Order', label: '#'},
  {key: 'Track', label: 'Track'},
  {key: 'Year-Semester', label: 'Semester'},
  {key: 'Class', label: 'Class'},
  {key: 'Team#', label: 'Team'},
  {key: 'TeamName', label: 'Team Name'},
  {key: 'Project Title', label: 'Project Title'},
  {key: 'Organization', label: 'Organization'},
  {key: 'Industry', label: 'Industry'},
];

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  setPage: (update: (current: number) => number) => void;
}

const SheetsPagination = ({currentPage, totalPages, setPage}: PaginationProps) => (
  <nav className="itg-pagination sdt-pagination" aria-label="Project pages">
    <button
      type="button"
      className="itg-pagination-link sdt-page-btn"
      disabled={currentPage === 0}
      onClick={() => setPage((current) => Math.max(0, current - 1))}
    >
      Previous
    </button>
    <span className="itg-pagination-info sdt-page-info">
      Page {currentPage + 1} of {totalPages}
    </span>
    <button
      type="button"
      className="itg-pagination-link sdt-page-btn"
      disabled={currentPage >= totalPages - 1}
      onClick={() => setPage((current) => Math.min(totalPages - 1, current + 1))}
    >
      Next
    </button>
  </nav>
);

/** A searchable, sortable, paged table of project rows from a Google Sheet (event archive pages). */
export const SheetsDataTable = ({rows, loading, error, columns: columnsProp, initialSearch}: SheetsDataTableProps) => {
  const columns = columnsProp || DEFAULT_COLUMNS;
  const [searchParams] = useSearchParams();
  const table = useSheetsTable(rows, initialSearch ?? (searchParams.get('value') || ''), columns[0]?.key || 'Track');
  const {sortField, sortDir} = table;
  const handleSort = table.sortBy;

  if (loading) return <div className="sdt-loading">Loading project data...</div>;
  if (error) return <div className="sdt-error">{error}</div>;

  return (
    <div className="sdt-container" id="projects">
      <div className="sdt-controls">
        <input
          className="itg-input sdt-search"
          type="search"
          aria-label="Search projects"
          placeholder="Search projects..."
          value={table.search}
          onChange={(event) => table.searchFor(event.target.value)}
        />
        <span className="sdt-count" aria-live="polite">
          {table.filteredCount} of {rows.length} projects
        </span>
      </div>

      <div className="itg-table-wrap sdt-table-wrap">
        <table className="itg-table sdt-table">
          <thead>
            <tr>
              {columns.map((column) => {
                const active = sortField === column.key;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    className={`sdt-th ${active ? `sdt-sorted-${sortDir}` : ''}`}
                    aria-sort={
                      active
                        ? sortDir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                    }
                  >
                    <button
                      type="button"
                      className="sdt-sort-button"
                      onClick={() => handleSort(column.key)}
                    >
                      {column.label}
                    </button>
                  </th>
                );
              })}
              <th scope="col" className="sdt-th sdt-th-expand">
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {table.paged.length === 0 ? (
              <tr className="sdt-empty-row">
                <td colSpan={columns.length + 1}>
                  {rows.length === 0 ? 'No data available in table' : 'No matching records found'}
                </td>
              </tr>
            ) : null}
            {table.paged.map((item, index) => (
              <SheetsTableRow
                key={item.key}
                item={item}
                index={index}
                columns={columns}
                sortField={sortField}
                isExpanded={table.expandedKey === item.key}
                onToggle={() => table.setExpandedKey(table.expandedKey === item.key ? null : item.key)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {table.totalPages > 1 ? (
        <SheetsPagination currentPage={table.currentPage} totalPages={table.totalPages} setPage={table.setPage} />
      ) : null}
    </div>
  );
};
