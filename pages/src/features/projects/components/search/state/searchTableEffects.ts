import {useCallback, useEffect, useRef, type Dispatch, type SetStateAction} from 'react';
import {type ProjectCatalogCopy} from '@/features/projects/catalog/projectCatalog';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import type {SearchTableState} from './types';

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
export function useTableRefresh({
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
export function useTableFocus(searchTables: SearchTableState[]) {
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
