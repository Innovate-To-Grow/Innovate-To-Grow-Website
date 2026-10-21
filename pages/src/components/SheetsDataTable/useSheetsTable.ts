import {useMemo, useState} from 'react';
import {identifyRows} from './rowIdentity';
import type {SheetRow} from './types';

export type SortField = keyof SheetRow;
export type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 10;
const SEARCHED_FIELDS: SortField[] = [
  'Team#',
  'TeamName',
  'Project Title',
  'Organization',
  'Industry',
  'Class',
  'Track',
  'Year-Semester',
];

/** Search, sort, paging and the one expanded row of a sheet-backed project table. */
export function useSheetsTable(rows: SheetRow[], initialSearch: string, defaultSortField: SortField) {
  const [search, setSearch] = useState(initialSearch);
  const [sortField, setSortField] = useState<SortField>(defaultSortField);
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const identifiedRows = useMemo(() => identifyRows(rows), [rows]);

  const filtered = useMemo(() => {
    if (!search) return identifiedRows;
    const q = search.toLowerCase();
    return identifiedRows.filter(({row}) => SEARCHED_FIELDS.some((field) => row[field].toLowerCase().includes(q)));
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

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const currentPage = Math.min(page, Math.max(totalPages - 1, 0));
  const paged = sorted.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  const sortBy = (field: SortField) => {
    if (sortField === field) {
      setSortDir((direction) => (direction === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
    setPage(0);
  };

  const searchFor = (value: string) => {
    setSearch(value);
    setPage(0);
    setExpandedKey(null);
  };

  return {
    search,
    searchFor,
    sortField,
    sortDir,
    sortBy,
    expandedKey,
    setExpandedKey,
    filteredCount: filtered.length,
    paged,
    currentPage,
    totalPages,
    setPage,
  };
}
