import {useRef, useState} from 'react';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {createAISearchRunner, type UpdateSearchTable} from './aiSearchRunner';
import {useTableFocus, useTableRefresh} from './searchTableEffects';
import type {SearchTableState} from './types';

export type {SearchTableState} from './types';

/** The first table's id; it is the one seeded with the page's initial search. */
export const initialSearchTableId = (idPrefix: string) => `${idPrefix}-1`;

/** A table's heading: its own title, else "AI Search Table", else "Search Table" (numbered when several). */
export function searchTableTitle(table: SearchTableState, tables: SearchTableState[]) {
  if (table.title) return table.title;
  if (table.type === 'ai') return 'AI Search Table';
  const standardIds = tables.filter((candidate) => candidate.type === 'standard').map((candidate) => candidate.id);
  return standardIds.length === 1 ? 'Search Table' : `Search Table ${standardIds.indexOf(table.id) + 1}`;
}

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
