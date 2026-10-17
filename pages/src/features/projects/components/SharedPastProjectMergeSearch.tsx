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
import {
  createProjectGridFingerprint,
  type ProjectGridRow,
} from './projectGrid';

const INITIAL_SEARCH_TABLE: SearchTableState = {id: 'shared-search-table-1', type: 'standard'};
const AI_SEARCH_LIMIT = 10;

const createAISearchTableTitle = (query: string) => {
  const normalized = query.trim().replace(/\s+/g, ' ');
  const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}...` : normalized;
  return `AI Search Table: ${clipped}`;
};

const pluralize = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

// The share API refuses more rows than this (PastProjectShareSerializer.validate_rows).
const MAX_SHARED_ROWS = 1000;

const describeAddResult = ({
  added,
  alreadyAdded,
  failed,
  unavailable,
}: {
  added: number;
  alreadyAdded: number;
  failed: number;
  unavailable: number;
}): Pick<SearchTableSaveResult, 'tone' | 'message'> => {
  const parts: string[] = [];
  if (added) {
    parts.push(`${pluralize(added, 'project')} added.`);
  }
  if (alreadyAdded) {
    parts.push(
      added || failed || unavailable
        ? `${pluralize(alreadyAdded, 'project')} ${alreadyAdded === 1 ? 'was' : 'were'} already in this shared result.`
        : 'Those projects are already in this shared result.',
    );
  }
  if (unavailable) {
    parts.push(
      `${pluralize(unavailable, 'project')} ${unavailable === 1 ? 'is' : 'are'} no longer in the archive ` +
        `and ${unavailable === 1 ? 'was' : 'were'} skipped.`,
    );
  }
  if (failed) {
    parts.push(
      `${pluralize(failed, 'project')} could not be loaded and ${failed === 1 ? 'is' : 'are'} still selected. ` +
        'Click Add Selected to try again.',
    );
  }
  return {tone: failed || (unavailable && !added) ? 'error' : added ? 'success' : 'info', message: parts.join(' ')};
};

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
  const tableSequence = useRef(1);
  const pendingRefreshTableId = useRef<string | null>(null);
  const lastSeenRows = useRef(rows);

  const currentFingerprints = useMemo(
    () => new Set(currentRows.map((row) => createProjectGridFingerprint(row))),
    [currentRows],
  );
  // The content fingerprint deliberately ignores `id`, so a compact archive row never
  // matches the hydrated copy of the same project already in this share. Match on the
  // project id as well, or already-included projects are offered (and added) again.
  const currentProjectIds = useMemo(
    () => new Set(currentRows.flatMap((row) => (row.id ? [row.id] : []))),
    [currentRows],
  );
  const isAlreadyShared = useCallback(
    (row: ProjectGridRow) =>
      (Boolean(row.id) && currentProjectIds.has(row.id as string)) ||
      currentFingerprints.has(createProjectGridFingerprint(row)),
    [currentFingerprints, currentProjectIds],
  );
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
  const handleMergeSelected = useCallback(
    async (selected: ProjectGridRow[], {reportProgress}: SearchTableSaveHelpers): Promise<SearchTableSaveResult> => {
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
        const seenFingerprints = new Set(currentFingerprints);
        const seenIds = new Set(currentProjectIds);
        const rowsToAppend: ProjectGridRow[] = [];
        let alreadyAdded = selected.length - toAdd.length;
        loadedRows.forEach((row, index) => {
          if (skipped.has(index)) {
            return;
          }
          const fingerprint = createProjectGridFingerprint(row);
          if (seenFingerprints.has(fingerprint) || (row.id && seenIds.has(row.id))) {
            alreadyAdded += 1;
            return;
          }
          seenFingerprints.add(fingerprint);
          if (row.id) seenIds.add(row.id);
          rowsToAppend.push(row);
        });

        const appended = rowsToAppend.length ? await onAddRows(rowsToAppend) : 0;
        const added = typeof appended === 'number' ? appended : rowsToAppend.length;
        const result = describeAddResult({
          added,
          alreadyAdded: alreadyAdded + (rowsToAppend.length - added),
          failed: failedIndexes.length,
          unavailable: unavailableIndexes.length,
        });
        return {...result, retainedIndexes: failedIndexes.map((index) => toAdd[index])};
      } catch {
        // Keep the user's selection so they can retry without re-checking rows.
        return {
          tone: 'error',
          message: 'Unable to add selected projects. They are still selected, so you can try again.',
        };
      } finally {
        saveControllers.current.delete(controller);
        setIsSaving(false);
      }
    },
    [currentFingerprints, currentProjectIds, currentRows.length, isAlreadyShared, onAddRows],
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
