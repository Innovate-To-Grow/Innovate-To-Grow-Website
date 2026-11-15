import {useEffect, useMemo, useState} from 'react';
import {
  createProjectGridFingerprint,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from '../contracts/projectGrid';
import {useGridPagination} from './useGridPagination';
import {useRowKeySet} from './useRowKeySet';
import {
  useExpandedRows,
  useFilteredSortedRows,
  type UseProjectGridTableOptions,
  useSeededSearch,
  useStartOverOnServerRows,
} from './projectGridTableHooks';

/** Default choices for the “rows per page” control (hook merges in the current size if needed). */
export const PROJECT_GRID_PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100] as const;

const NO_CLASS_LABELS: Record<string, string> = {};

export function useProjectGridTable({
  rows,
  pageSize: initialPageSize = 10,
  pageSizeOptions: pageSizeChoices = PROJECT_GRID_PAGE_SIZE_OPTIONS,
  defaultSortField,
  defaultSortDirection = 'asc',
  initialSortField = defaultSortField,
  initialSortDirection = defaultSortDirection,
  initialPage = 0,
  initialSearch = '',
  filterRow,
  classLabels = NO_CLASS_LABELS,
  searchRemote,
}: UseProjectGridTableOptions) {
  const [search, setSearch] = useSeededSearch(initialSearch);
  const [sortField, setSortField] = useState<ProjectGridColumnKey>(initialSortField);
  const [sortDirection, setSortDirection] = useState<ProjectGridSortDirection>(initialSortDirection);
  const {filteredRows, sortedRows, serverAnswer} = useFilteredSortedRows(
    rows,
    {search, filterRow, classLabels, searchRemote},
    sortField,
    sortDirection,
  );
  // Every table that uses this hook starts a new search on its first page.
  const paging = useGridPagination(sortedRows, {initialPageSize, pageSizeChoices, initialPage, resetKey: search});
  const {setPage} = paging;
  const serverSearch = useStartOverOnServerRows(search, serverAnswer, setPage);
  const {expandedKeys, expanded, allDetailsExpanded, toggleAllDetails} = useExpandedRows(rows);
  const [selectedKeys, selected] = useRowKeySet();

  // Rows the user has explicitly checked (independent of the current search
  // filter), in the table's natural order. Drives "merge only what I selected".
  const selectedRows = useMemo(
    () => rows.filter((row) => selectedKeys.has(row.__key)),
    [rows, selectedKeys],
  );

  useEffect(() => {
    const rowKeys = new Set(rows.map((row) => row.__key));

    // Prune expanded/selected keys for rows that no longer exist when `rows` changes,
    // while keeping the rest of the user's expand/selection state. Both updaters read
    // prior state, so this stale-key cleanup is genuine React-to-prop sync, not a value
    // derivable in render.
    expanded.retainOnly(rowKeys);
    selected.retainOnly(rowKeys);
  }, [rows, expanded, selected]);

  const toggleSort = (field: ProjectGridColumnKey) => {
    if (field === sortField) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
    setPage(0);
  };

  /** Sort by a field in a given direction (the Sort by select names both). */
  const setSort = (field: ProjectGridColumnKey, direction: ProjectGridSortDirection) => {
    setSortField(field);
    setSortDirection(direction);
    setPage(0);
  };

  // Start over as a newly mounted table would, for when the rows are replaced by a reload.
  const reset = () => {
    paging.resetPaging();
    setSearch(initialSearch);
    setSortField(defaultSortField);
    setSortDirection(defaultSortDirection);
    expanded.replace([]);
    selected.replace([]);
  };

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
    setSort,
    pageSize: paging.pageSize,
    setPageSize: paging.setPageSize,
    pageSizeOptions: paging.pageSizeOptions,
    page: paging.page,
    setPage,
    totalPages: paging.totalPages,
    filteredRows,
    sortedRows,
    serverSearch,
    selectedRows,
    pagedRows: paging.pagedRows,
    expandedKeys,
    toggleExpanded: expanded.toggle,
    selectedKeys,
    toggleSelected: selected.toggle,
    clearSelection: () => selected.replace([]),
    // Replace the selection with exactly the given rows. Used for a filter-aware "select all" that
    // must not reach rows hidden by the active search (so a later bulk delete can't remove unseen rows).
    selectRows: (rowsToSelect: ProjectGridItem[]) => selected.replace(rowsToSelect.map((row) => row.__key)),
    // Add rows to the selection, keeping rows already checked under an earlier search.
    addToSelection: (rowsToSelect: ProjectGridItem[]) => selected.add(rowsToSelect.map((row) => row.__key)),
    removeFromSelection: selected.remove,
    reset,
    toggleAllDetails,
    allDetailsExpanded,
    hasSelection: selectedKeys.size > 0,
    removeSelectedRows: (sourceRows: ProjectGridItem[]) => sourceRows.filter((row) => !selectedKeys.has(row.__key)),
    keepSelectedRows: (sourceRows: ProjectGridItem[]) => sourceRows.filter((row) => selectedKeys.has(row.__key)),
    fingerprints,
  };
}
