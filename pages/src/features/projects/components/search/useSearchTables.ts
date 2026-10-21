import {useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction} from 'react';
import {searchPastProjectsWithAI, toProjectGridRow} from '@/features/projects/api';
import type {ProjectGridRow} from '../projectGrid';

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
  const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}...` : normalized;
  return `AI Search Table: ${clipped}`;
};

const getAISearchErrorMessage = (error: unknown) => {
  const payload = (error as {response?: {data?: {detail?: string; message?: string}}}).response?.data;
  return payload?.detail || payload?.message || 'AI search is unavailable right now. Please try again.';
};

/** A table's heading: its own title, else "AI Search Table", else "Search Table" (numbered when several). */
export function searchTableTitle(table: SearchTableState, tables: SearchTableState[]) {
  if (table.title) return table.title;
  if (table.type === 'ai') return 'AI Search Table';
  const standardIds = tables.filter((candidate) => candidate.type === 'standard').map((candidate) => candidate.id);
  return standardIds.length === 1 ? 'Search Table' : `Search Table ${standardIds.indexOf(table.id) + 1}`;
}

type AISearchResponse = Awaited<ReturnType<typeof searchPastProjectsWithAI>>;

/** The rows and title an AI search loads into its table, or why it loads none. */
const aiSearchOutcome = (
  response: AISearchResponse,
  query: string,
  filterAIRows: (rows: ProjectGridRow[]) => ProjectGridRow[],
  allAIRowsFilteredMessage: string,
): {error: string} | {rows: ProjectGridRow[]; title: string} => {
  if (!response.available) {
    return {error: response.message || 'AI search is unavailable right now.'};
  }
  const aiRows = filterAIRows(response.results.map(toProjectGridRow));
  if (!aiRows.length) {
    return {error: response.results.length ? allAIRowsFilteredMessage : 'AI search did not find matching past projects.'};
  }
  return {rows: aiRows, title: createAISearchTableTitle(response.query || query)};
};

interface UseTableRefreshOptions {
  rows: ProjectGridRow[];
  setSearchTables: Dispatch<SetStateAction<SearchTableState[]>>;
  onRefreshRows?: () => void;
  onMessage: (message: string) => void;
  refreshingMessage: string;
}

/** Refreshing one table from a refetched archive; returns the per-table refresh action. */
function useTableRefresh({rows, setSearchTables, onRefreshRows, onMessage, refreshingMessage}: UseTableRefreshOptions) {
  const pendingRefreshTableId = useRef<string | null>(null);
  const lastSeenRows = useRef(rows);

  // Refresh is per-table: the refetch keeps serving stale rows (so the stack stays mounted and
  // every other table keeps its local curation), and once the fresh archive lands as a new `rows`
  // array, only the table that asked is reset — via its resetKey — with the new data. The card stays
  // mounted, so a save it has running still reports its outcome there.
  useEffect(() => {
    if (rows === lastSeenRows.current) {
      return;
    }
    lastSeenRows.current = rows;
    const tableId = pendingRefreshTableId.current;
    if (!tableId) {
      return;
    }
    pendingRefreshTableId.current = null;
    setSearchTables((current) =>
      current.map((table) => (table.id === tableId ? {...table, rowsResetKey: (table.rowsResetKey ?? 0) + 1} : table)),
    );
    onMessage('Search table refreshed from the latest past-project archive.');
  }, [rows, onMessage, setSearchTables]);

  return useCallback(
    (tableId: string) => {
      pendingRefreshTableId.current = tableId;
      onRefreshRows?.();
      onMessage(refreshingMessage);
    },
    [onRefreshRows, onMessage, refreshingMessage],
  );
}

interface UseSearchTablesOptions {
  /** Table ids are `${idPrefix}-1`, `${idPrefix}-2`, … */
  idPrefix: string;
  isAuthenticated: boolean;
  /** The past-project archive every standard table searches. */
  rows: ProjectGridRow[];
  onRefreshRows?: () => void;
  onMessage: (message: string) => void;
  /** Drops AI results this page cannot use (e.g. projects already on the shared page). */
  filterAIRows?: (rows: ProjectGridRow[]) => ProjectGridRow[];
  /** When every AI result was filtered out. */
  allAIRowsFilteredMessage?: string;
  /** Shown while a standard table reloads the archive. */
  refreshingMessage: string;
}

/** A stack of search tables: standard archive searches plus at most one AI search table. */
export function useSearchTables({
  idPrefix,
  isAuthenticated,
  rows,
  onRefreshRows,
  onMessage,
  filterAIRows = (aiRows) => aiRows,
  allAIRowsFilteredMessage = 'AI search did not find matching past projects.',
  refreshingMessage,
}: UseSearchTablesOptions) {
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [
    {id: initialSearchTableId(idPrefix), type: 'standard'},
  ]);
  const tableSequence = useRef(1);
  const hasAISearchTable = searchTables.some((table) => table.type === 'ai');

  const nextTableId = () => {
    tableSequence.current += 1;
    return `${idPrefix}-${tableSequence.current}`;
  };

  const updateSearchTable = (tableId: string, update: (table: SearchTableState) => SearchTableState) => {
    setSearchTables((current) => current.map((table) => (table.id === tableId ? update(table) : table)));
  };

  const addSearchTable = () => {
    const id = nextTableId();
    setSearchTables((current) => [...current, {id, type: 'standard'}]);
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
      onMessage('');
    }
    return true;
  };

  const runAISearch = async (tableId: string, query: string) => {
    if (!isAuthenticated) {
      return;
    }
    const finish = (message: string, messageTone: SearchTableState['messageTone'], extra = {}) =>
      updateSearchTable(tableId, (table) => ({...table, isLoading: false, message, messageTone, ...extra}));

    updateSearchTable(tableId, (table) => ({
      ...table,
      isLoading: true,
      message: 'Searching past projects with AI...',
      messageTone: 'loading',
    }));
    try {
      const outcome = aiSearchOutcome(await searchPastProjectsWithAI(query, AI_SEARCH_LIMIT), query, filterAIRows, allAIRowsFilteredMessage);
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

  const removeSearchTable = (tableId: string) => {
    setSearchTables((current) => current.filter((table) => table.id !== tableId));
  };

  const refreshSearchTable = useTableRefresh({rows, setSearchTables, onRefreshRows, onMessage, refreshingMessage});

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
