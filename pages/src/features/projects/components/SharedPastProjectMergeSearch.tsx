import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {buildLoginPath} from '@/features/auth/api/redirects';
import {
  hydrateProjectGridRowsSettled,
  needsProjectGridHydration,
  searchPastProjectsWithAI,
  toProjectGridRow,
} from '@/features/projects/api';
import {PastProjectsAIStatus} from './builder/PastProjectsAIStatus';
import {PastProjectsAISearchForm} from './builder/PastProjectsAISearchForm';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {SearchTableCard, type SearchTableSaveHelpers, type SearchTableSaveResult} from './SearchTableCard';
import {createProjectGridRowMatcher, type ProjectGridRow} from './projectGrid';
import {RELOADED_WHILE_SAVING, describeSaveResult} from './saveResults';

const INITIAL_SEARCH_TABLE: SearchTableState = {id: 'shared-search-table-1', type: 'standard'};
const AI_SEARCH_LIMIT = 10;

const createAISearchTableTitle = (query: string) => {
  const normalized = query.trim().replace(/\s+/g, ' ');
  const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}...` : normalized;
  return `AI Search Table: ${clipped}`;
};

// The share API refuses more rows than this (PastProjectShareSerializer.validate_rows).
const MAX_SHARED_ROWS = 1000;

const getAISearchErrorMessage = (error: unknown) => {
  const payload = (error as {response?: {data?: {detail?: string; message?: string}}}).response?.data;
  return payload?.detail || payload?.message || 'AI search is unavailable right now. Please try again.';
};

interface SharedPastProjectMergeSearchProps {
  currentRows: ProjectGridRow[];
  error: string | null;
  loading: boolean;
  rows: ProjectGridRow[];
  /** Adds the rows to the share; may resolve to how many were actually appended (others were already there). */
  onAddRows: (rows: ProjectGridRow[]) => Promise<number | void>;
  onRefreshRows?: () => void;
}

interface SearchTableState {
  id: string;
  initialRows?: ProjectGridRow[];
  isLoading?: boolean;
  message?: string;
  messageTone?: 'error' | 'loading' | 'success';
  rowsResetKey?: number;
  title?: string;
  type: 'standard' | 'ai';
}

export const SharedPastProjectMergeSearch = ({
  currentRows,
  error,
  loading,
  rows,
  onAddRows,
  onRefreshRows,
}: SharedPastProjectMergeSearchProps) => {
  const {isAuthenticated} = useAuth();
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
  const [builderMessage, setBuilderMessage] = useState('');
  const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const saveControllers = useRef(new Set<AbortController>());
  // Reloading a search table (Refresh, new AI results) replaces its card. An add that finishes afterwards has
  // lost the card that would show its outcome, so the outcome is carried over to the new one.
  const tableGenerations = useRef(new Map<string, number>());
  const carrySequence = useRef(0);
  const [carriedStatuses, setCarriedStatuses] = useState<
    Record<string, {token: number; result: SearchTableSaveResult}>
  >({});
  const tableSequence = useRef(1);
  const pendingRefreshTableId = useRef<string | null>(null);
  const lastSeenRows = useRef(rows);

  // Matches on project id as well as content: a compact archive row never has the fingerprint of the hydrated
  // copy of the same project already in this share, which would otherwise be offered (and added) again.
  const isAlreadyShared = useMemo(() => createProjectGridRowMatcher(currentRows).has, [currentRows]);
  const availableRows = useMemo(
    () => rows.filter((row) => !isAlreadyShared(row)),
    [isAlreadyShared, rows],
  );
  const hasAISearchTable = searchTables.some((table) => table.type === 'ai');
  const standardSearchTableIds = searchTables.filter((table) => table.type === 'standard').map((table) => table.id);
  const standardSearchTableCount = standardSearchTableIds.length;

  const handleAddSearchTable = () => {
    tableSequence.current += 1;
    const id = `shared-search-table-${tableSequence.current}`;
    setSearchTables((current) => [...current, {id, type: 'standard'}]);
    setBuilderMessage('');
  };

  const handleAddAISearchTable = () => {
    if (!isAuthenticated) {
      setIsAISearchLoginDialogOpen(true);
      return;
    }

    if (hasAISearchTable) {
      return;
    }

    tableSequence.current += 1;
    const id = `shared-search-table-${tableSequence.current}`;
    setSearchTables((current) => [
      ...current,
      {
        id,
        initialRows: [],
        rowsResetKey: 0,
        title: 'AI Search Table',
        type: 'ai',
      },
    ]);
    setBuilderMessage('');
  };

  const updateSearchTable = (tableId: string, update: (table: SearchTableState) => SearchTableState) => {
    setSearchTables((current) => current.map((table) => (table.id === tableId ? update(table) : table)));
  };

  const markTableReloaded = (tableId: string) => {
    tableGenerations.current.set(tableId, (tableGenerations.current.get(tableId) ?? 0) + 1);
  };

  const handleAISearch = async (tableId: string, query: string) => {
    if (!isAuthenticated) {
      return;
    }

    updateSearchTable(tableId, (table) => ({
      ...table,
      isLoading: true,
      message: 'Searching past projects with AI...',
      messageTone: 'loading',
    }));
    try {
      const response = await searchPastProjectsWithAI(query, AI_SEARCH_LIMIT);
      if (!response.available) {
        updateSearchTable(tableId, (table) => ({
          ...table,
          isLoading: false,
          message: response.message || 'AI search is unavailable right now.',
          messageTone: 'error',
        }));
        return;
      }

      const aiRows = response.results
        .map(toProjectGridRow)
        .filter((row) => !isAlreadyShared(row));

      if (!aiRows.length) {
        updateSearchTable(tableId, (table) => ({
          ...table,
          isLoading: false,
          message: response.results.length
            ? 'AI found projects that are already in this shared result.'
            : 'AI search did not find matching past projects.',
          messageTone: 'error',
        }));
        return;
      }

      markTableReloaded(tableId);
      updateSearchTable(tableId, (table) => ({
        ...table,
        initialRows: aiRows,
        isLoading: false,
        message: `${aiRows.length} AI result${aiRows.length === 1 ? '' : 's'} loaded into this table.`,
        messageTone: 'success',
        rowsResetKey: (table.rowsResetKey ?? 0) + 1,
        title: createAISearchTableTitle(response.query || query),
      }));
      setBuilderMessage('');
    } catch (err) {
      updateSearchTable(tableId, (table) => ({
        ...table,
        isLoading: false,
        message: getAISearchErrorMessage(err),
        messageTone: 'error',
      }));
    }
  };

  const handleRemoveSearchTable = (tableId: string) => {
    setSearchTables((current) => current.filter((table) => table.id !== tableId));
  };

  // Refresh is per-table: the refetch keeps serving stale rows (so the stack stays mounted and
  // every other table keeps its local curation), and once the fresh archive lands as a new `rows`
  // array, only the table that asked is remounted — via its key — with the new data.
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
    tableGenerations.current.set(tableId, (tableGenerations.current.get(tableId) ?? 0) + 1);
    setSearchTables((current) =>
      current.map((table) =>
        table.id === tableId ? {...table, rowsResetKey: (table.rowsResetKey ?? 0) + 1} : table,
      ),
    );
    setBuilderMessage('Search table refreshed from the latest past-project archive.');
  }, [rows]);

  const handleRefreshSearchTable = useCallback(
    (tableId: string) => {
      pendingRefreshTableId.current = tableId;
      onRefreshRows?.();
      setBuilderMessage('Refreshing this full-archive search table from the latest past-project data...');
    },
    [onRefreshRows],
  );

  // Leaving the page cancels the detail requests of an add still in flight.
  useEffect(() => {
    const controllers = saveControllers.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, []);

  // Save = add a single search table's checked rows into the shared result. Projects already in the
  // shared result (by id or fingerprint) are skipped so each project is stored once. The outcome is
  // reported inside the table that added them.
  const addSelectedRows = useCallback(
    async (
      selected: ProjectGridRow[],
      reportProgress: SearchTableSaveHelpers['reportProgress'],
      replaced: () => boolean,
    ): Promise<SearchTableSaveResult> => {
      // Projects already shared need no detail request.
      const toAdd = selected.flatMap((row, index) => (isAlreadyShared(row) ? [] : [index]));
      if (currentRows.length + toAdd.length > MAX_SHARED_ROWS) {
        return {
          tone: 'error',
          message: `A shared page can include at most ${MAX_SHARED_ROWS} projects. Select fewer projects and try again.`,
        };
      }

      const controller = new AbortController();
      saveControllers.current.add(controller);
      setIsSaving(true);
      setBuilderMessage('');
      try {
        // Archive rows arrive compact, with no abstract or student names. Saving them as they are
        // would write those fields away as blank for everyone who opens the share, and the detail
        // endpoint is the only place that content lives. Fill them in first, as the builder does.
        const pendingRows = toAdd.map((index) => selected[index]);
        const {rows: loadedRows, failedIndexes, unavailableIndexes} = pendingRows.some(needsProjectGridHydration)
          ? await hydrateProjectGridRowsSettled(pendingRows, {signal: controller.signal, onProgress: reportProgress})
          : {rows: pendingRows, failedIndexes: [] as number[], unavailableIndexes: [] as number[]};

        const skipped = new Set([...failedIndexes, ...unavailableIndexes]);
        const shared = createProjectGridRowMatcher(currentRows);
        const rowsToAppend: ProjectGridRow[] = [];
        let alreadyAdded = selected.length - toAdd.length;
        loadedRows.forEach((row, index) => {
          if (skipped.has(index)) {
            return;
          }
          if (shared.has(row)) {
            alreadyAdded += 1;
            return;
          }
          shared.add(row);
          rowsToAppend.push(row);
        });

        const appended = rowsToAppend.length ? await onAddRows(rowsToAppend) : 0;
        const added = typeof appended === 'number' ? appended : rowsToAppend.length;
        const result = describeSaveResult(
          {
            added,
            alreadySaved: alreadyAdded + (rowsToAppend.length - added),
            failed: failedIndexes.length,
            unavailable: unavailableIndexes.length,
          },
          {
            added: 'added.',
            already: 'in this shared result',
            place: 'in this shared result',
            retryLabel: 'Add Selected',
            selectionKept: !replaced(),
          },
        );
        return {...result, retainedIndexes: failedIndexes.map((index) => toAdd[index])};
      } catch {
        // Keep the user's selection so they can retry without re-checking rows.
        return {
          tone: 'error',
          message: replaced()
            ? 'Unable to add selected projects. Select them again and click Add Selected to try again.'
            : 'Unable to add selected projects. They are still selected, so you can try again.',
        };
      } finally {
        saveControllers.current.delete(controller);
        setIsSaving(false);
      }
    },
    [currentRows, isAlreadyShared, onAddRows],
  );

  const handleMergeSelected = useCallback(
    async (
      selected: ProjectGridRow[],
      {tableId, reportProgress}: SearchTableSaveHelpers,
    ): Promise<SearchTableSaveResult> => {
      const generation = tableGenerations.current.get(tableId) ?? 0;
      const replaced = () => (tableGenerations.current.get(tableId) ?? 0) !== generation;
      const result = await addSelectedRows(selected, reportProgress, replaced);
      if (replaced()) {
        carrySequence.current += 1;
        const carried = {
          token: carrySequence.current,
          result: {...result, message: `${RELOADED_WHILE_SAVING} ${result.message}`},
        };
        setCarriedStatuses((current) => ({...current, [tableId]: carried}));
      }
      return result;
    },
    [addSelectedRows],
  );

  return (
    <div className="shared-past-project-merge-search">
      <PastProjectsActionBar
        builderMessage={builderMessage}
        error={error}
        loading={loading || isSaving}
        title="Add Projects from Full Archive"
        saveLabel="Add Selected"
        saveTarget="this shared page"
        savedLabel="Added"
        aiSearchDisabled={hasAISearchTable}
        aiSearchLoginRequired={!isAuthenticated}
        onAddAISearchTable={handleAddAISearchTable}
        onAddSearchTable={handleAddSearchTable}
      />

      {isAISearchLoginDialogOpen ? (
        <PastProjectsDialog
          title="Sign in required"
          cancelLabel="Close"
          confirmLabel="Sign In"
          onCancel={() => setIsAISearchLoginDialogOpen(false)}
          onConfirm={() => {
            window.location.href = buildLoginPath(`${window.location.pathname}${window.location.search}`);
          }}
        >
          <p>You need to sign in before using AI search.</p>
        </PastProjectsDialog>
      ) : null}

      {loading ? <div className="project-grid-card"><div className="project-grid-state">Loading past projects...</div></div> : null}
      {error ? <div className="project-grid-card"><div className="project-grid-state project-grid-state-error">{error}</div></div> : null}

      {!loading && !error ? (
        <div className="search-table-stack">
          {searchTables.map((table) => {
            const isAISearchTable = table.type === 'ai';
            const title =
              table.title ??
              (isAISearchTable
                ? 'AI Search Table'
                : standardSearchTableCount === 1
                  ? 'Search Table'
                  : `Search Table ${standardSearchTableIds.indexOf(table.id) + 1}`);

            return (
              <SearchTableCard
                key={table.rowsResetKey === undefined ? table.id : `${table.id}-${table.rowsResetKey}`}
                canRemove={searchTables.length > 1}
                mergeLabel="Add Selected"
                mergeVerb="Add"
                mergingVerb="Adding"
                mergeDisabled={isSaving}
                isRowSaved={isAlreadyShared}
                savedRowLabel="Added"
                carriedOverStatus={carriedStatuses[table.id] ?? null}
                description={
                  isAISearchTable
                    ? 'Use AI to load matching past projects into this table, then check the projects you want and click Add Selected.'
                    : 'Search the full past-project archive for additional projects to add to this shared result.'
                }
                emptyMessage={
                  isAISearchTable
                    ? 'Run AI search to load projects into this table.'
                    : undefined
                }
                initialRows={table.initialRows ?? availableRows}
                controlsStatus={
                  table.message && table.messageTone && table.messageTone !== 'loading' ? (
                    <PastProjectsAIStatus message={table.message} tone={table.messageTone} />
                  ) : undefined
                }
                searchControl={
                  isAISearchTable ? (
                    <PastProjectsAISearchForm
                      isAuthenticated={isAuthenticated}
                      loading={Boolean(table.isLoading)}
                      onSearch={(query) => handleAISearch(table.id, query)}
                    />
                  ) : undefined
                }
                tableId={table.id}
                title={title}
                className={
                  isAISearchTable
                    ? `is-ai-search-table${table.rowsResetKey ? ' has-ai-results' : ''}`
                    : undefined
                }
                resultsMotionKey={isAISearchTable ? table.rowsResetKey : undefined}
                onRemove={handleRemoveSearchTable}
                onRefresh={isAISearchTable || !onRefreshRows ? undefined : handleRefreshSearchTable}
                onMergeSelected={handleMergeSelected}
              />
            );
          })}

          {!searchTables.length ? (
            <div className="project-grid-card project-grid-empty-shell">
              <div className="project-grid-empty">
                No search tables are open. Add a new table to search for more projects.
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
