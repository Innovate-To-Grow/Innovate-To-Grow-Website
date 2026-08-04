import {Fragment, useMemo, useState} from 'react';
import {useSearchParams} from 'react-router';
import type {SheetRow} from './types';
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

type SortField = keyof SheetRow;
type SortDir = 'asc' | 'desc';

interface IdentifiedRow {
  key: string;
  detailId: string;
  row: SheetRow;
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

const normalizeIdentityValue = (value: string) =>
  value.trim().toLocaleLowerCase().replace(/\s+/g, ' ');

const rowIdentityBase = (row: SheetRow) =>
  [
    row['Year-Semester'],
    row.Class,
    row['Team#'],
    row.TeamName,
    row['Project Title'],
  ].map(normalizeIdentityValue).join('\u001f');

const rowIdentity = (row: SheetRow) => {
  const fullFingerprint = Object.keys(row)
    .sort()
    .map((field) => normalizeIdentityValue(row[field as keyof SheetRow]))
    .join('\u001f');
  return `${rowIdentityBase(row)}\u001e${fullFingerprint}`;
};

const stableDomToken = (value: string) => {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
};

export const SheetsDataTable = ({
  rows,
  loading,
  error,
  columns: columnsProp,
  initialSearch,
}: SheetsDataTableProps) => {
  const columns = columnsProp || DEFAULT_COLUMNS;
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(
    () => initialSearch ?? (searchParams.get('value') || ''),
  );
  const [sortField, setSortField] = useState<SortField>(
    columns[0]?.key || 'Track',
  );
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 10;

  const identifiedRows = useMemo<IdentifiedRow[]>(
    () => {
      const occurrences = new Map<string, number>();
      return rows.map((row) => {
        const identity = rowIdentity(row);
        const occurrence = occurrences.get(identity) ?? 0;
        occurrences.set(identity, occurrence + 1);
        // The occurrence suffix is used only for byte-for-byte duplicate rows,
        // which have no domain distinction. All meaningful row identity remains
        // stable across insertion, refresh, and reordering.
        const key = occurrence ? `${identity}\u001d${occurrence}` : identity;
        return {
          key,
          detailId: `sdt-detail-${stableDomToken(key)}`,
          row,
        };
      });
    },
    [rows],
  );

  const filtered = useMemo(() => {
    if (!search) return identifiedRows;
    const q = search.toLowerCase();
    return identifiedRows.filter(({row}) =>
      [
        row['Team#'],
        row.TeamName,
        row['Project Title'],
        row.Organization,
        row.Industry,
        row.Class,
        row.Track,
        row['Year-Semester'],
      ].some((value) => value.toLowerCase().includes(q)),
    );
  }, [identifiedRows, search]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = a.row[sortField] || '';
      const bv = b.row[sortField] || '';
      const cmp = av.localeCompare(bv, undefined, {numeric: true});
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sortField, sortDir]);

  const totalPages = Math.ceil(sorted.length / pageSize);
  const currentPage = Math.min(page, Math.max(totalPages - 1, 0));
  const paged = sorted.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize,
  );

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((direction) =>
        direction === 'asc' ? 'desc' : 'asc',
      );
    } else {
      setSortField(field);
      setSortDir('asc');
    }
    setPage(0);
  };

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(0);
    setExpandedKey(null);
  };

  if (loading)
    return <div className="sdt-loading">Loading project data...</div>;
  if (error) return <div className="sdt-error">{error}</div>;

  return (
    <div className="sdt-container" id="projects">
      <div className="sdt-controls">
        <input
          className="sdt-search"
          type="search"
          aria-label="Search projects"
          placeholder="Search projects..."
          value={search}
          onChange={(event) => handleSearch(event.target.value)}
        />
        <span className="sdt-count" aria-live="polite">
          {filtered.length} of {rows.length} projects
        </span>
      </div>

      <div className="sdt-table-wrap">
        <table className="sdt-table">
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
              <th
                scope="col"
                className="sdt-th sdt-th-expand"
                aria-label="Project details"
              />
            </tr>
          </thead>
          <tbody>
            {paged.map(({key, detailId, row}) => {
              const isExpanded = expandedKey === key;
              const hasDetails = Boolean(
                row.Abstract || row['Student Names'],
              );
              return (
                <Fragment key={key}>
                  <tr className={isExpanded ? 'sdt-row-expanded' : ''}>
                    {columns.map((column) => (
                      <td key={column.key} className="sdt-td">
                        {row[column.key]}
                      </td>
                    ))}
                    <td className="sdt-td sdt-td-expand">
                      {hasDetails ? (
                        <button
                          type="button"
                          className="sdt-expand-button"
                          aria-label={`${
                            isExpanded ? 'Hide' : 'Show'
                          } details for ${row['Project Title'] || row.TeamName}`}
                          aria-expanded={isExpanded}
                          aria-controls={detailId}
                          onClick={() =>
                            setExpandedKey(isExpanded ? null : key)
                          }
                        >
                          {isExpanded ? '\u25B2' : '\u25BC'}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                  {isExpanded ? (
                    <tr className="sdt-detail-row">
                      <td
                        id={detailId}
                        colSpan={columns.length + 1}
                        className="sdt-detail-cell"
                      >
                        {row.Abstract ? (
                          <div className="sdt-detail-section">
                            <strong>Abstract:</strong> {row.Abstract}
                          </div>
                        ) : null}
                        {row['Student Names'] ? (
                          <div className="sdt-detail-section">
                            <strong>Student Names:</strong>{' '}
                            {row['Student Names']}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 ? (
        <div className="sdt-pagination">
          <button
            type="button"
            className="sdt-page-btn"
            disabled={currentPage === 0}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
          >
            Previous
          </button>
          <span className="sdt-page-info">
            Page {currentPage + 1} of {totalPages}
          </span>
          <button
            type="button"
            className="sdt-page-btn"
            disabled={currentPage >= totalPages - 1}
            onClick={() =>
              setPage((current) =>
                Math.min(totalPages - 1, current + 1),
              )
            }
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
};
