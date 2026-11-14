import {useDeferredValue, useEffect, useMemo, useState} from 'react';
import {
  getProjectGridSearchValue,
  hasProjectGridDetails,
  normalizeSearchText,
  sortProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from '../contracts/projectGrid';
import type {ProjectGridServerSearch} from '../contracts/gridTableProps';
import {useRemoteSearchMatches, type RemoteRowSearch} from './useRemoteSearchMatches';
import {useRowKeySet} from './useRowKeySet';

export interface UseProjectGridTableOptions {
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
export function useFilteredSortedRows(
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
export function useStartOverOnServerRows(
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
export function useExpandedRows(rows: ProjectGridItem[]) {
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
export function useSeededSearch(initialSearch: string) {
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
