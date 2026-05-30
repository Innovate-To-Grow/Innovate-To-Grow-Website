import {useState, useMemo} from 'react';
import {useSearchParams} from 'react-router-dom';
import type {SheetRow} from './types';

interface ColumnDef {
  key: SortField;
  label: string;
}

interface SheetsDataTableProps {
  rows: SheetRow[];
  loading?: boolean;
  error?: string | null;
  columns?: ColumnDef[];
  /** Controlled initial search value. When changed externally, syncs to local state. */
  initialSearch?: string;
}

type SortField = keyof SheetRow;
type SortDir = 'asc' | 'desc';

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

export const SheetsDataTable = ({rows, loading, error, columns: columnsProp, initialSearch}: SheetsDataTableProps) => {
  const columns = columnsProp || DEFAULT_COLUMNS;
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => initialSearch ?? (searchParams.get('value') || ''));
  const [sortField, setSortField] = useState<SortField>(columns[0]?.key || 'Track');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 10;

  const filtered = useMemo(() => {
    if (!search) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (r) =>
        r['Team#'].toLowerCase().includes(q) ||
        r.TeamName.toLowerCase().includes(q) ||
        r['Project Title'].toLowerCase().includes(q) ||
        r.Organization.toLowerCase().includes(q) ||
        r.Industry.toLowerCase().includes(q) ||
        r.Class.toLowerCase().includes(q) ||
        r.Track.toLowerCase().includes(q) ||
        r['Year-Semester'].toLowerCase().includes(q),
    );
  }, [rows, search]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = a[sortField] || '';
      const bv = b[sortField] || '';
      const cmp = av.localeCompare(bv, undefined, {numeric: true});
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sortField, sortDir]);

  const totalPages = Math.ceil(sorted.length / pageSize);
  const paged = sorted.slice(page * pageSize, (page + 1) * pageSize);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
    setPage(0);
  };

  const handleSearch = (val: string) => {
    setSearch(val);
    setPage(0);
    setExpandedIdx(null);
  };

  if (loading) return <div className="sdt-loading">Loading project data...</div>;
  if (error) return <div className="sdt-error">{error}</div>;

  return (
    <div className="sdt-container" id="projects">
      <div className="sdt-controls">
        <input
          className="sdt-search"
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
        />
        <span className="sdt-count">
          {filtered.length} of {rows.length} projects
        </span>
      </div>

      <div className="sdt-table-wrap">
        <table className="sdt-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`sdt-th ${sortField === col.key ? `sdt-sorted-${sortDir}` : ''}`}
                  onClick={() => handleSort(col.key)}
                >
                  {col.label}
                </th>
              ))}
              <th className="sdt-th sdt-th-expand" />
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => {
              const globalIdx = page * pageSize + i;
              const isExpanded = expandedIdx === globalIdx;
              return (
                <tr key={globalIdx} className={isExpanded ? 'sdt-row-expanded' : ''}>
                  {columns.map((col) => (
                    <td key={col.key} className="sdt-td">
                      {row[col.key]}
                    </td>
                  ))}
                  <td
                    className="sdt-td sdt-td-expand"
                    onClick={() => setExpandedIdx(isExpanded ? null : globalIdx)}
                  >
                    {row.Abstract || row['Student Names'] ? (isExpanded ? '\u25B2' : '\u25BC') : ''}
                  </td>
                </tr>
              );
            })}
            {expandedIdx !== null &&
              expandedIdx >= page * pageSize &&
              expandedIdx < (page + 1) * pageSize && (
                <tr className="sdt-detail-row">
                  <td colSpan={columns.length + 1} className="sdt-detail-cell">
                    {sorted[expandedIdx]?.Abstract && (
                      <div className="sdt-detail-section">
                        <strong>Abstract:</strong> {sorted[expandedIdx].Abstract}
                      </div>
                    )}
                    {sorted[expandedIdx]?.['Student Names'] && (
                      <div className="sdt-detail-section">
                        <strong>Student Names:</strong> {sorted[expandedIdx]['Student Names']}
                      </div>
                    )}
                  </td>
                </tr>
              )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="sdt-pagination">
          <button
            className="sdt-page-btn"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="sdt-page-info">
            Page {page + 1} of {totalPages}
          </span>
          <button
            className="sdt-page-btn"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
