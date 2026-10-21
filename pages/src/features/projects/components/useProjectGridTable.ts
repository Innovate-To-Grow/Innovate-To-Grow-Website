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
import {useGridPagination} from './grid/useGridPagination';
import {useRowKeySet} from './grid/useRowKeySet';

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
  /** Seed every expandable row open on mount (used by the shared, read-only view). */
  expandAllByDefault?: boolean;
  /** Extra filter applied with the search (e.g. the Class and Industry selects). Keep its identity stable. */
  filterRow?: (row: ProjectGridItem) => boolean;
}

/** The rows the search (and the extra filter) keeps, in the chosen sort order. */
function useFilteredSortedRows(
  rows: ProjectGridItem[],
  search: string,
  filterRow: UseProjectGridTableOptions['filterRow'],
  sortField: ProjectGridColumnKey,
  sortDirection: ProjectGridSortDirection,
) {
  const deferredSearch = useDeferredValue(search);
  const filteredRows = useMemo(() => {
    const candidates = filterRow ? rows.filter(filterRow) : rows;
    if (!deferredSearch.trim()) {
      return candidates;
    }
    const query = deferredSearch.trim().toLowerCase();
    return candidates.filter((row) => getProjectGridSearchValue(row).includes(query));
  }, [deferredSearch, filterRow, rows]);

  const sortedRows = useMemo(
    () => sortProjectGridItems(filteredRows, sortField, sortDirection),
    [filteredRows, sortDirection, sortField],
  );
  return {filteredRows, sortedRows};
}

/** Expanded rows: the keys of rows with details, whether all are open, and opening them all on mount if asked. */
function useExpandedRows(rows: ProjectGridItem[], expandAllByDefault: boolean) {
  const [expandedKeys, expanded] = useRowKeySet();
  const expandableKeys = useMemo(
    () => rows.filter((row) => hasProjectGridDetails(row)).map((row) => row.__key),
    [rows],
  );
  const allDetailsExpanded =
    expandableKeys.length > 0 && expandableKeys.every((rowKey) => expandedKeys.has(rowKey));

  useEffect(() => {
    if (!expandAllByDefault) {
      return;
    }
    // Seed every expandable row open. Adding an already-present key is a no-op, so a
    // user can still collapse rows afterward without this re-expanding them. The
    // functional updater merges into prior expand state derived from rows/props, so it
    // cannot be replaced by a render-time derivation without dropping user toggles.
    expanded.add(expandableKeys);
  }, [expandAllByDefault, expandableKeys, expanded]);

  const toggleAllDetails = () => {
    expanded.replace(allDetailsExpanded ? [] : expandableKeys);
  };
  return {expandedKeys, expanded, allDetailsExpanded, toggleAllDetails};
}

export function useProjectGridTable({
  rows,
  pageSize: initialPageSize = 10,
  pageSizeOptions: pageSizeChoices = PROJECT_GRID_PAGE_SIZE_OPTIONS,
  defaultSortField,
  defaultSortDirection = 'asc',
  initialSearch = '',
  expandAllByDefault = false,
  filterRow,
}: UseProjectGridTableOptions) {
  const [search, setSearch] = useState(initialSearch);
  const [sortField, setSortField] = useState<ProjectGridColumnKey>(defaultSortField);
  const [sortDirection, setSortDirection] = useState<ProjectGridSortDirection>(defaultSortDirection);
  const {filteredRows, sortedRows} = useFilteredSortedRows(rows, search, filterRow, sortField, sortDirection);
  const paging = useGridPagination(sortedRows, initialPageSize, pageSizeChoices);
  const {setPage} = paging;
  const {expandedKeys, expanded, allDetailsExpanded, toggleAllDetails} = useExpandedRows(rows, expandAllByDefault);
  const [selectedKeys, selected] = useRowKeySet();

  useEffect(() => {
    // Reset the user's in-progress search when the seed prop changes (it tracks the
    // ?value= URL param / external team search, which can change while mounted).
    // `search` holds intervening user input, so this is a genuine prop-change reset,
    // not a derivable value. Doing it during render with a previous-prop ref would
    // shift the update from after-paint to render-phase — an observable timing change
    // we must not introduce — so the effect-phase sync stays.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- external prop-change reset; render-phase alternative would change effect timing
    setSearch(initialSearch);
  }, [initialSearch]);

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
    pageSize: paging.pageSize,
    setPageSize: paging.setPageSize,
    pageSizeOptions: paging.pageSizeOptions,
    page: paging.page,
    setPage,
    totalPages: paging.totalPages,
    filteredRows,
    sortedRows,
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
