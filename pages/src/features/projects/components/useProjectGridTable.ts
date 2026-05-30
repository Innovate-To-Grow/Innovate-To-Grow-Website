import {useDeferredValue, useEffect, useMemo, useState} from 'react';
import {
  createProjectGridFingerprint,
  getProjectGridSearchValue,
  hasProjectGridDetails,
  sortProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from './projectGrid';

/** Default choices for the “rows per page” control (hook merges in the current size if needed). */
export const PROJECT_GRID_PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100] as const;

interface UseProjectGridTableOptions {
  rows: ProjectGridItem[];
  /** Initial rows per page; user can change this via the table control. */
  pageSize?: number;
  /** Allowed page sizes in the dropdown; current size is always included. */
  pageSizeOptions?: readonly number[];
  defaultSortField: ProjectGridColumnKey;
  defaultSortDirection?: ProjectGridSortDirection;
  initialSearch?: string;
}

export function useProjectGridTable({
  rows,
  pageSize: initialPageSize = 10,
  pageSizeOptions: pageSizeChoices = PROJECT_GRID_PAGE_SIZE_OPTIONS,
  defaultSortField,
  defaultSortDirection = 'asc',
  initialSearch = '',
}: UseProjectGridTableOptions) {
  const [pageSize, setPageSizeState] = useState(() => Math.max(1, initialPageSize));
  const [search, setSearch] = useState(initialSearch);
  const deferredSearch = useDeferredValue(search);
  const [sortField, setSortField] = useState<ProjectGridColumnKey>(defaultSortField);
  const [sortDirection, setSortDirection] = useState<ProjectGridSortDirection>(defaultSortDirection);
  const [page, setPage] = useState(0);

  const pageSizeOptions = useMemo(() => {
    const merged = new Set<number>([...pageSizeChoices, pageSize]);
    return Array.from(merged).sort((a, b) => a - b);
  }, [pageSize, pageSizeChoices]);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    setSearch(initialSearch);
  }, [initialSearch]);

  const filteredRows = useMemo(() => {
    if (!deferredSearch.trim()) {
      return rows;
    }
    const query = deferredSearch.trim().toLowerCase();
    return rows.filter((row) => getProjectGridSearchValue(row).includes(query));
  }, [deferredSearch, rows]);

  const sortedRows = useMemo(
    () => sortProjectGridItems(filteredRows, sortField, sortDirection),
    [filteredRows, sortDirection, sortField],
  );

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const currentPage = Math.min(page, totalPages - 1);

  const pagedRows = useMemo(
    () => sortedRows.slice(currentPage * pageSize, (currentPage + 1) * pageSize),
    [currentPage, pageSize, sortedRows],
  );

  const setPageSize = (next: number) => {
    const size = Math.max(1, Math.floor(next));
    setPageSizeState(size);
    setPage(0);
  };

  const expandableKeys = useMemo(
    () => rows.filter((row) => hasProjectGridDetails(row)).map((row) => row.__key),
    [rows],
  );

  const allDetailsExpanded =
    expandableKeys.length > 0 && expandableKeys.every((rowKey) => expandedKeys.has(rowKey));

  useEffect(() => {
    if (currentPage !== page) {
      setPage(currentPage);
    }
  }, [currentPage, page]);

  useEffect(() => {
    const rowKeys = new Set(rows.map((row) => row.__key));

    setExpandedKeys((current) => {
      const next = new Set<string>();
      current.forEach((rowKey) => {
        if (rowKeys.has(rowKey)) {
          next.add(rowKey);
        }
      });
      return next;
    });

    setSelectedKeys((current) => {
      const next = new Set<string>();
      current.forEach((rowKey) => {
        if (rowKeys.has(rowKey)) {
          next.add(rowKey);
        }
      });
      return next;
    });
  }, [rows]);

  const toggleSort = (field: ProjectGridColumnKey) => {
    if (field === sortField) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
    setPage(0);
  };

  const toggleExpanded = (rowKey: string) => {
    setExpandedKeys((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) {
        next.delete(rowKey);
      } else {
        next.add(rowKey);
      }
      return next;
    });
  };

  const toggleSelected = (rowKey: string) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) {
        next.delete(rowKey);
      } else {
        next.add(rowKey);
      }
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedKeys(new Set());
  };

  const selectAllRows = () => {
    setSelectedKeys(new Set(rows.map((row) => row.__key)));
  };

  const toggleAllDetails = () => {
    if (allDetailsExpanded) {
      setExpandedKeys(new Set());
      return;
    }
    setExpandedKeys(new Set(expandableKeys));
  };

  const removeSelectedRows = (sourceRows: ProjectGridItem[]) =>
    sourceRows.filter((row) => !selectedKeys.has(row.__key));

  const keepSelectedRows = (sourceRows: ProjectGridItem[]) =>
    sourceRows.filter((row) => selectedKeys.has(row.__key));

  const fingerprints = useMemo(
    () => new Set(rows.map((row) => createProjectGridFingerprint(row))),
    [rows],
  );

  return {
    search,
    setSearch,
    sortField,
    sortDirection,
    toggleSort,
    pageSize,
    setPageSize,
    pageSizeOptions,
    page: currentPage,
    setPage,
    totalPages,
    filteredRows,
    sortedRows,
    pagedRows,
    expandedKeys,
    toggleExpanded,
    selectedKeys,
    toggleSelected,
    clearSelection,
    selectAllRows,
    toggleAllDetails,
    allDetailsExpanded,
    hasSelection: selectedKeys.size > 0,
    removeSelectedRows,
    keepSelectedRows,
    fingerprints,
  };
}
