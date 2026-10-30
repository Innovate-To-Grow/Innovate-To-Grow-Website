import {useDeferredValue, useEffect, useMemo, useState} from 'react';
import {
  createProjectGridFingerprint,
  getProjectGridSearchValue,
  hasProjectGridDetails,
  normalizeSearchText,
  sortProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from '../contracts/projectGrid';
import {useGridPagination} from './useGridPagination';
import {useRemoteSearchMatches, type RemoteRowSearch} from './useRemoteSearchMatches';
import {useRowKeySet} from './useRowKeySet';

/** Default choices for the “rows per page” control (hook merges in the current size if needed). */
export const PROJECT_GRID_PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100] as const;

const NO_CLASS_LABELS: Record<string, string> = {};

interface UseProjectGridTableOptions {
  rows: ProjectGridItem[];
  /** Initial rows per page; user can change this via the table control. */
  pageSize?: number;
  /** Allowed page sizes in the dropdown; current size is always included. */
  pageSizeOptions?: readonly number[];
  defaultSortField: ProjectGridColumnKey;
  defaultSortDirection?: ProjectGridSortDirection;
  /** The sort to start with when it is not the default (e.g. restored from the URL); `reset` still goes back to the default. */
  initialSortField?: ProjectGridColumnKey;
  initialSortDirection?: ProjectGridSortDirection;
  /** The page to start on (0-based), e.g. restored from the URL. */
  initialPage?: number;
  initialSearch?: string;
  /** Seed every expandable row open on mount (used by the shared, read-only view). */
  expandAllByDefault?: boolean;
  /** Extra filter applied with the search (e.g. the Class and Industry selects). Keep its identity stable. */
  filterRow?: (row: ProjectGridItem) => boolean;
  /** Class names by code ("CAP" -> "Engineering Capstone"), so a search finds a team by its class name. */
  classLabels?: Record<string, string>;
  /**
   * Asks the server which projects match a search, for text the rows do not carry (a compact archive row has no
   * abstract). Rows it names are kept along with those the rows' own text matches; `searchPending` is true until it
   * has answered the current search. Keep its identity stable.
   */
  searchRemote?: RemoteRowSearch;
}

interface RowFilters {
  search: string;
  filterRow: UseProjectGridTableOptions['filterRow'];
  classLabels: Record<string, string>;
  searchRemote: UseProjectGridTableOptions['searchRemote'];
}

/** The rows the search (and the extra filter) keeps, in the chosen sort order. */
function useFilteredSortedRows(
  rows: ProjectGridItem[],
  {search, filterRow, classLabels, searchRemote}: RowFilters,
  sortField: ProjectGridColumnKey,
  sortDirection: ProjectGridSortDirection,
) {
  const deferredSearch = useDeferredValue(search);
  const remote = useRemoteSearchMatches(deferredSearch, searchRemote);
  const remoteMatches = remote.matches;
  // Built once per set of rows, not on every keystroke: normalizing 920 archive rows is not free.
  const searchValues = useMemo(
    () => new Map(rows.map((row) => [row.__key, getProjectGridSearchValue(row, classLabels)])),
    [classLabels, rows],
  );
  const filteredRows = useMemo(() => {
    const candidates = filterRow ? rows.filter(filterRow) : rows;
    const query = normalizeSearchText(deferredSearch);
    if (!query) {
      return candidates;
    }
    return candidates.filter(
      (row) => searchValues.get(row.__key)?.includes(query) || Boolean(row.id && remoteMatches?.has(row.id)),
    );
  }, [deferredSearch, filterRow, remoteMatches, rows, searchValues]);

  const sortedRows = useMemo(
    () => sortProjectGridItems(filteredRows, sortField, sortDirection),
    [filteredRows, sortDirection, sortField],
  );
  return {filteredRows, sortedRows, searchPending: remote.pending};
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

/** The search, started from `initialSearch` and started over whenever that seed changes while mounted. */
function useSeededSearch(initialSearch: string) {
  const [search, setSearch] = useState(initialSearch);

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

  return [search, setSearch] as const;
}

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
  expandAllByDefault = false,
  filterRow,
  classLabels = NO_CLASS_LABELS,
  searchRemote,
}: UseProjectGridTableOptions) {
  const [search, setSearch] = useSeededSearch(initialSearch);
  const [sortField, setSortField] = useState<ProjectGridColumnKey>(initialSortField);
  const [sortDirection, setSortDirection] = useState<ProjectGridSortDirection>(initialSortDirection);
  const {filteredRows, sortedRows, searchPending} = useFilteredSortedRows(
    rows,
    {search, filterRow, classLabels, searchRemote},
    sortField,
    sortDirection,
  );
  // Every table that uses this hook starts a new search on its first page.
  const paging = useGridPagination(sortedRows, {initialPageSize, pageSizeChoices, initialPage, resetKey: search});
  const {setPage} = paging;
  const {expandedKeys, expanded, allDetailsExpanded, toggleAllDetails} = useExpandedRows(rows, expandAllByDefault);
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
    searchPending,
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
