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
import type {ProjectGridServerSearch} from '../contracts/gridTableProps';
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
  /** Extra filter applied with the search (e.g. the Class and Industry selects). Keep its identity stable. */
  filterRow?: (row: ProjectGridItem) => boolean;
  /** Class names by code ("CAP" -> "Engineering Capstone"), so a search finds a team by its class name. */
  classLabels?: Record<string, string>;
  /**
   * Asks the server which projects match a search, for text the rows do not carry (a compact archive row has no
   * abstract). Rows it names are kept along with those the rows' own text matches; `serverSearch` says what it has
   * done for the current search. Keep its identity stable.
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
  const query = normalizeSearchText(deferredSearch);
  // Built once per set of rows, not on every keystroke: normalizing 920 archive rows is not free.
  const searchValues = useMemo(
    () => new Map(rows.map((row) => [row.__key, getProjectGridSearchValue(row, classLabels)])),
    [classLabels, rows],
  );
  const candidates = useMemo(() => (filterRow ? rows.filter(filterRow) : rows), [filterRow, rows]);
  const ownMatches = useMemo(
    () => (query ? candidates.filter((row) => searchValues.get(row.__key)?.includes(query)) : candidates),
    [candidates, query, searchValues],
  );
  // The server can only add rows whose own text the search missed: with none left, it is not asked.
  const serverCanAdd = ownMatches.length < candidates.length;
  const remote = useRemoteSearchMatches(deferredSearch, serverCanAdd ? searchRemote : undefined);
  const remoteMatches = remote.matches;
  const filteredRows = useMemo(() => {
    if (!remoteMatches) return ownMatches;
    const own = new Set(ownMatches);
    return candidates.filter((row) => own.has(row) || Boolean(row.id && remoteMatches.has(row.id)));
  }, [candidates, ownMatches, remoteMatches]);

  const sortedRows = useMemo(
    () => sortProjectGridItems(filteredRows, sortField, sortDirection),
    [filteredRows, sortDirection, sortField],
  );
  // The server's answer when it found rows the rows' own text did not (they are sorted in among those shown), as one
  // key of its ids: the same answer asked for again is a new Set, but the same key.
  const serverAddition = remoteMatches && filteredRows.length > ownMatches.length ? remoteMatches : null;
  const addedRowsKey = useMemo(() => (serverAddition ? [...serverAddition].sort().join(' ') : null), [serverAddition]);
  const serverAnswer: ProjectGridServerSearch = {
    pending: remote.pending,
    addedRowsKey,
    tooBroad: remote.tooBroad,
    failed: remote.failed,
  };
  return {filteredRows, sortedRows, serverAnswer};
}

/**
 * Back to the first page when the server's answer adds rows to a search: they are sorted in among the rows already
 * shown, so a later page the visitor moved to meanwhile would show other rows under the same "showing 11–15". Once
 * per answer and search: the same rows coming back (the search typed again, or asked again after rows were removed
 * and restored) do not start it over again. Returns the server search with the key of the answer it started over for.
 */
function useStartOverOnServerRows(
  search: string,
  answer: ProjectGridServerSearch,
  setPage: (page: number) => void,
): ProjectGridServerSearch {
  const {addedRowsKey} = answer;
  const [startedOver, setStartedOver] = useState<{search: string; addedRowsKey: string | null}>({search, addedRowsKey});
  // Adjusted during render, like the page clamp in useGridPagination.
  if (search !== startedOver.search) {
    // A new search starts on its first page anyway (useGridPagination's resetKey), and every answer to it is new.
    setStartedOver({search, addedRowsKey: null});
  } else if (addedRowsKey !== null && addedRowsKey !== startedOver.addedRowsKey) {
    setStartedOver({search, addedRowsKey});
    setPage(0);
  }
  return {...answer, addedRowsKey: startedOver.addedRowsKey};
}

/** Expanded rows (every row starts collapsed): the keys of rows with details, and whether all of them are open. */
function useExpandedRows(rows: ProjectGridItem[]) {
  const [expandedKeys, expanded] = useRowKeySet();
  const expandableKeys = useMemo(
    () => rows.filter((row) => hasProjectGridDetails(row)).map((row) => row.__key),
    [rows],
  );
  const allDetailsExpanded =
    expandableKeys.length > 0 && expandableKeys.every((rowKey) => expandedKeys.has(rowKey));

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
