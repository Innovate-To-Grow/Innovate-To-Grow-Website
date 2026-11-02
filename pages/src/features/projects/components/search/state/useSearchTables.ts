import {useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction} from 'react';
import {searchPastProjectsWithAI, toProjectGridRow, type ProjectAISearchScope} from '@/features/projects/api';
import {useProjectCatalog, type ProjectCatalogCopy} from '@/features/projects/catalog/projectCatalog';
import {collectFieldMessages} from '@/lib/api/errorMessages';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';

export interface SearchTableState {
  id: string;
  initialRows?: ProjectGridRow[];
  isLoading?: boolean;
  message?: string;
  messageTone?: 'error' | 'loading' | 'success';
  rowsResetKey?: number;
  title?: string;
  type: 'standard' | 'ai';
}

const AI_SEARCH_LIMIT = 10;

/** The first table's id; it is the one seeded with the page's initial search. */
export const initialSearchTableId = (idPrefix: string) => `${idPrefix}-1`;

const createAISearchTableTitle = (query: string) => {
  const normalized = query.trim().replace(/\s+/g, ' ');
  const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}…` : normalized;
  return `AI Search Table: ${clipped}`;
};

// The API's reason when it gives one: `detail` (budget, provider errors), `message`, or a validation error on a
// field (`{"query": ["Query must be at most 2000 characters."]}`), which a retry would only repeat.
const getAISearchErrorMessage = (error: unknown) => {
  const data = (error as {response?: {data?: unknown}} | null)?.response?.data;
  const [reason] =
    data && typeof data === 'object'
      ? collectFieldMessages(data as Record<string, unknown>, (message) => Boolean(message.trim()), ['code'])
      : [];
  return reason || 'AI search is unavailable right now. Please try again.';
};

// `available: false` means AI search is not set up on this site. The API's own message is meant for the site's
// administrators, so members get this instead.
const AI_SEARCH_NOT_AVAILABLE_MESSAGE =
  'AI search is not available on this site right now. You can still find projects with a regular search table.';

/** A table's heading: its own title, else "AI Search Table", else "Search Table" (numbered when several). */
export function searchTableTitle(table: SearchTableState, tables: SearchTableState[]) {
  if (table.title) return table.title;
  if (table.type === 'ai') return 'AI Search Table';
  const standardIds = tables.filter((candidate) => candidate.type === 'standard').map((candidate) => candidate.id);
  return standardIds.length === 1 ? 'Search Table' : `Search Table ${standardIds.indexOf(table.id) + 1}`;
}

type AISearchResponse = Awaited<ReturnType<typeof searchPastProjectsWithAI>>;

interface AIResultsOptions {
  filterAIRows: (rows: ProjectGridRow[]) => ProjectGridRow[];
  /** When every AI result was filtered out, and when AI search found none. */
  allAIRowsFilteredMessage: string;
  noResultsMessage: string;
}

/** The rows and title an AI search loads into its table, or why it loads none. */
const aiSearchOutcome = (
  response: AISearchResponse,
  query: string,
  {filterAIRows, allAIRowsFilteredMessage, noResultsMessage}: AIResultsOptions,
): {error: string} | {rows: ProjectGridRow[]; title: string} => {
  if (!response.available) {
    return {error: AI_SEARCH_NOT_AVAILABLE_MESSAGE};
  }
  const aiRows = filterAIRows(response.results.map(toProjectGridRow));
  if (!aiRows.length) {
    return {error: response.results.length ? allAIRowsFilteredMessage : noResultsMessage};
  }
  return {rows: aiRows, title: createAISearchTableTitle(response.query || query)};
};

interface UseTableRefreshOptions {
  rows: ProjectGridRow[];
  rowsError: string | null;
  setSearchTables: Dispatch<SetStateAction<SearchTableState[]>>;
  onRefreshRows?: () => void;
  onMessage: (message: string) => void;
  refreshingMessage: string;
  /** What a refresh says once the rows landed, or when they could not be loaded (the catalog's). */
  copy: Pick<ProjectCatalogCopy, 'refreshed' | 'refreshFailed'>;
}

/** Refreshing tables from a refetched archive; returns the per-table refresh action. */
function useTableRefresh({
  rows,
  rowsError,
  setSearchTables,
  onRefreshRows,
  onMessage,
  refreshingMessage,
  copy: {refreshed, refreshFailed},
}: UseTableRefreshOptions) {
  // Every table waiting for the refetch: another table may ask before the first refetch lands.
  const pendingTableIds = useRef(new Set<string>());
  const lastSeenRows = useRef(rows);

  const settlePending = useCallback(
    (update: (table: SearchTableState) => SearchTableState) => {
      const tableIds = pendingTableIds.current;
      pendingTableIds.current = new Set();
      setSearchTables((current) => current.map((table) => (tableIds.has(table.id) ? update(table) : table)));
      return tableIds.size;
    },
    [setSearchTables],
  );

  // Refresh is per-table: the refetch keeps serving stale rows (so the stack stays mounted and
  // every other table keeps its local curation), and once the fresh archive lands as a new `rows`
  // array, only the tables that asked are reset — via their resetKey — with the new data. A card stays
  // mounted, so a save it has running still reports its outcome there.
  useEffect(() => {
    if (rows === lastSeenRows.current) {
      return;
    }
    lastSeenRows.current = rows;
    if (!pendingTableIds.current.size) {
      return;
    }
    const count = settlePending((table) => ({...table, rowsResetKey: (table.rowsResetKey ?? 0) + 1}));
    onMessage(refreshed(count));
  }, [rows, onMessage, refreshed, settlePending]);

  // A failed refetch keeps serving the same rows, so only its error says so: the tables that asked keep
  // their rows and say they were not refreshed.
  useEffect(() => {
    if (!rowsError || !pendingTableIds.current.size) {
      return;
    }
    settlePending((table) => ({...table, message: refreshFailed, messageTone: 'error'}));
    onMessage('');
  }, [rowsError, onMessage, refreshFailed, settlePending]);

  return useCallback(
    (tableId: string) => {
      pendingTableIds.current.add(tableId);
      setSearchTables((current) =>
        current.map((table) => (table.id === tableId ? {...table, message: undefined, messageTone: undefined} : table)),
      );
      onRefreshRows?.();
      onMessage(refreshingMessage);
    },
    [onRefreshRows, onMessage, refreshingMessage, setSearchTables],
  );
}

/** Where focus goes once the stack has rendered: a new table's search field, or a table's heading. */
interface TableFocusRequest {
  tableId: string;
  target: 'field' | 'heading';
}

const focusSearchTable = ({tableId, target}: TableFocusRequest) => {
  const card = document.querySelector(`[data-search-table-id="${tableId}"]`);
  const element = card?.querySelector<HTMLElement>(target === 'field' ? 'input[type="search"]' : '.project-grid-card-title');
  element?.focus();
};

/**
 * A new table is added at the bottom of the page, out of view, and adding the AI table greys out its button;
 * deleting a table takes its Delete button with it. Focus follows the change instead of dropping to the page: to
 * the new table's search field, or to the heading of the table that was next to the deleted one.
 */
function useTableFocus(searchTables: SearchTableState[]) {
  const request = useRef<TableFocusRequest | null>(null);
  useEffect(() => {
    const pending = request.current;
    request.current = null;
    if (pending) {
      focusSearchTable(pending);
    }
  }, [searchTables]);
  return useCallback((next: TableFocusRequest) => {
    request.current = next;
  }, []);
}

type UpdateSearchTable = (tableId: string, update: (table: SearchTableState) => SearchTableState) => void;

interface AISearchRunnerOptions extends AIResultsOptions {
  isAuthenticated: boolean;
  updateSearchTable: UpdateSearchTable;
  /** What the search ranks (the catalog's), and what its table says while it runs. */
  scope: ProjectAISearchScope;
  searchingMessage: string;
  onMessage: (message: string) => void;
}

/** Runs an AI table's query and loads its results into that table, or says in it why there are none. */
const createAISearchRunner =
  ({isAuthenticated, updateSearchTable, scope, searchingMessage, onMessage, ...results}: AISearchRunnerOptions) =>
  async (tableId: string, query: string) => {
    if (!isAuthenticated) {
      return;
    }
    const finish = (message: string, messageTone: SearchTableState['messageTone'], extra = {}) =>
      updateSearchTable(tableId, (table) => ({...table, isLoading: false, message, messageTone, ...extra}));

    updateSearchTable(tableId, (table) => ({
      ...table,
      isLoading: true,
      message: searchingMessage,
      messageTone: 'loading',
    }));
    try {
      const outcome = aiSearchOutcome(await searchPastProjectsWithAI(query, AI_SEARCH_LIMIT, scope), query, results);
      if ('error' in outcome) {
        finish(outcome.error, 'error');
        return;
      }
      updateSearchTable(tableId, (table) => ({
        ...table,
        initialRows: outcome.rows,
        isLoading: false,
        message: `${outcome.rows.length} AI result${outcome.rows.length === 1 ? '' : 's'} loaded into this table.`,
        messageTone: 'success',
        rowsResetKey: (table.rowsResetKey ?? 0) + 1,
        title: outcome.title,
      }));
      onMessage('');
    } catch (err) {
      finish(getAISearchErrorMessage(err), 'error');
    }
  };

interface UseSearchTablesOptions {
  /** Table ids are `${idPrefix}-1`, `${idPrefix}-2`, … */
  idPrefix: string;
  isAuthenticated: boolean;
  /** The past-project archive every standard table searches. */
  rows: ProjectGridRow[];
  /** Why the archive's latest (re)load failed; a failed refresh keeps `rows`. */
  rowsError?: string | null;
  onRefreshRows?: () => void;
  onMessage: (message: string) => void;
  /** Drops AI results this page cannot use (e.g. projects already on the shared page). */
  filterAIRows?: (rows: ProjectGridRow[]) => ProjectGridRow[];
  /** When every AI result was filtered out. Left out, the catalog's "did not find" message. */
  allAIRowsFilteredMessage?: string;
  /** Shown while a standard table reloads its rows. Left out, the catalog's. */
  refreshingMessage?: string;
}

/**
 * A stack of search tables: standard searches over the page's list plus at most one AI search table. The list's
 * AI scope and the messages naming it come from the page's ProjectCatalog.
 */
export function useSearchTables({
  idPrefix,
  isAuthenticated,
  rows,
  rowsError = null,
  onRefreshRows,
  onMessage,
  filterAIRows = (aiRows) => aiRows,
  allAIRowsFilteredMessage,
  refreshingMessage,
}: UseSearchTablesOptions) {
  const {aiScope, copy} = useProjectCatalog();
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [
    {id: initialSearchTableId(idPrefix), type: 'standard'},
  ]);
  const tableSequence = useRef(1);
  const hasAISearchTable = searchTables.some((table) => table.type === 'ai');
  const focusAfterRender = useTableFocus(searchTables);

  const nextTableId = () => {
    tableSequence.current += 1;
    return `${idPrefix}-${tableSequence.current}`;
  };

  const updateSearchTable: UpdateSearchTable = (tableId, update) => {
    setSearchTables((current) => current.map((table) => (table.id === tableId ? update(table) : table)));
  };

  const addSearchTable = () => {
    const id = nextTableId();
    setSearchTables((current) => [...current, {id, type: 'standard'}]);
    focusAfterRender({tableId: id, target: 'field'});
    onMessage('');
  };

  /** Returns false when the visitor must sign in first. */
  const addAISearchTable = () => {
    if (!isAuthenticated) {
      return false;
    }
    if (!hasAISearchTable) {
      const id = nextTableId();
      setSearchTables((current) => [
        ...current,
        {id, initialRows: [], rowsResetKey: 0, title: 'AI Search Table', type: 'ai'},
      ]);
      focusAfterRender({tableId: id, target: 'field'});
      onMessage('');
    }
    return true;
  };

  const runAISearch = createAISearchRunner({
    isAuthenticated,
    updateSearchTable,
    scope: aiScope,
    searchingMessage: copy.aiSearching,
    filterAIRows,
    allAIRowsFilteredMessage: allAIRowsFilteredMessage ?? copy.aiNoResults,
    noResultsMessage: copy.aiNoResults,
    onMessage,
  });

  const removeSearchTable = (tableId: string) => {
    const index = searchTables.findIndex((table) => table.id === tableId);
    const neighbour = searchTables[index - 1] ?? searchTables[index + 1];
    if (neighbour) {
      focusAfterRender({tableId: neighbour.id, target: 'heading'});
    }
    setSearchTables((current) => current.filter((table) => table.id !== tableId));
  };

  const refreshSearchTable = useTableRefresh({
    rows,
    rowsError,
    setSearchTables,
    onRefreshRows,
    onMessage,
    refreshingMessage: refreshingMessage ?? copy.refreshing,
    copy,
  });

  return {
    searchTables,
    hasAISearchTable,
    addSearchTable,
    addAISearchTable,
    runAISearch,
    removeSearchTable,
    refreshSearchTable,
  };
}
