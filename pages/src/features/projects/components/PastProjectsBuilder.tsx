import {useCallback, useEffect, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {buildLoginPath} from '@/features/auth/api/redirects';
import {searchPastProjectsWithAI, toProjectGridRow} from '@/features/projects/api';
import {PastProjectsAIStatus} from './builder/PastProjectsAIStatus';
import {PastProjectsAISearchForm} from './builder/PastProjectsAISearchForm';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {MergedResultsTable, type PastProjectShareCreationResult} from './MergedResultsTable';
import {SearchTableCard} from './SearchTableCard';
import {
  createProjectGridFingerprint,
  createProjectGridItems,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

const INITIAL_SEARCH_TABLE: SearchTableState = {id: 'search-table-1', type: 'standard'};

const AI_SEARCH_LIMIT = 10;

// The merged results live in component state, but creating a share requires signing in, and the
// login button navigates away with a full-page reload (window.location) — which would wipe an
// in-progress merge. Persist the merged rows in sessionStorage so they survive the login
// round-trip (and any reload) within the tab; they are restored on mount and dropped once a share
// is successfully created. sessionStorage (not localStorage) keeps the draft scoped to the tab
// session, so it does not leak into a later, unrelated visit.
const MERGED_ROWS_STORAGE_KEY = 'past-projects:builder:merged-rows';

const readPersistedMergedRows = (): ProjectGridRow[] => {
  try {
    const raw = sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ProjectGridRow[]) : [];
  } catch {
    return [];
  }
};

const writePersistedMergedRows = (rows: ProjectGridRow[]) => {
  try {
    if (rows.length) {
      sessionStorage.setItem(MERGED_ROWS_STORAGE_KEY, JSON.stringify(rows));
    } else {
      sessionStorage.removeItem(MERGED_ROWS_STORAGE_KEY);
    }
  } catch {
    // sessionStorage can throw (private mode / quota / disabled) — degrade to in-memory only.
  }
};

const clearPersistedMergedRows = () => {
  try {
    sessionStorage.removeItem(MERGED_ROWS_STORAGE_KEY);
  } catch {
    // ignore — nothing to clean up if storage is unavailable.
  }
};

const createAISearchTableTitle = (query: string) => {
  const normalized = query.trim().replace(/\s+/g, ' ');
  const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}...` : normalized;
  return `AI Search Table: ${clipped}`;
};

const getAISearchErrorMessage = (error: unknown) => {
  const payload = (error as {response?: {data?: {detail?: string; message?: string}}}).response?.data;
  return payload?.detail || payload?.message || 'AI search is unavailable right now. Please try again.';
};

interface PastProjectsBuilderProps {
  error: string | null;
  loading: boolean;
  rows: ProjectGridRow[];
  onRefreshRows?: () => void;
  onCreateShare: (
    rows: ProjectGridRow[],
    name: string,
    note: string,
  ) => Promise<PastProjectShareCreationResult>;
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

export const PastProjectsBuilder = ({
  error,
  loading,
  rows,
  onRefreshRows,
  onCreateShare,
}: PastProjectsBuilderProps) => {
  const {isAuthenticated} = useAuth();
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
  // Seed from any draft persisted before a login reload so the merged results survive the round-trip.
  const [mergedRows, setMergedRows] = useState<ProjectGridItem[]>(() =>
    createProjectGridItems(readPersistedMergedRows(), 'restored'),
  );
  const [mergedRowsUndo, setMergedRowsUndo] = useState<ProjectGridItem[] | null>(null);
  const [builderMessage, setBuilderMessage] = useState('');
  const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
  const tableSequence = useRef(1);
  const mergeSequence = useRef(0);
  const pendingRefreshTableId = useRef<string | null>(null);
  const lastSeenRows = useRef(rows);

  const hasAISearchTable = searchTables.some((table) => table.type === 'ai');
  const standardSearchTableIds = searchTables.filter((table) => table.type === 'standard').map((table) => table.id);
  const standardSearchTableCount = standardSearchTableIds.length;

  // Mirror the merged results into sessionStorage on every change so however the visitor leaves
  // (the login reload, a manual refresh, SPA navigation), the draft can be restored on return.
  useEffect(() => {
    writePersistedMergedRows(mergedRows.map(stripProjectGridItem));
  }, [mergedRows]);

  // Drop the persisted draft when the user logs out within the same tab, so a different user who
  // signs in next on a shared machine does not inherit the previous user's merged selection. The
  // login round-trip is a full page reload, so this never fires mid-flow — the component remounts
  // already authenticated and restores from sessionStorage in the state initializer above.
  const wasAuthenticatedRef = useRef(isAuthenticated);
  useEffect(() => {
    if (wasAuthenticatedRef.current && !isAuthenticated) {
      clearPersistedMergedRows();
      setMergedRows([]);
      setMergedRowsUndo(null);
    }
    wasAuthenticatedRef.current = isAuthenticated;
  }, [isAuthenticated]);

  // Wrap the parent's share creator so a *successful* share drops the persisted draft — the share
  // now owns this snapshot, and returning to the builder should start clean. A failed attempt keeps
  // the draft so the user does not lose their merged rows.
  const handleCreateShare = useCallback(
    async (shareRows: ProjectGridRow[], name: string, note: string) => {
      const result = await onCreateShare(shareRows, name, note);
      clearPersistedMergedRows();
      return result;
    },
    [onCreateShare],
  );

  const handleAddSearchTable = () => {
    tableSequence.current += 1;
    const id = `search-table-${tableSequence.current}`;
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
    const id = `search-table-${tableSequence.current}`;
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

      const aiRows = response.results.map(toProjectGridRow);
      if (!aiRows.length) {
        updateSearchTable(tableId, (table) => ({
          ...table,
          isLoading: false,
          message: 'AI search did not find matching past projects.',
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
      setBuilderMessage('Refreshing this search table from the latest past-project archive...');
    },
    [onRefreshRows],
  );

  // Save = merge a single search table's checked rows into the saved results. Duplicates already
  // saved (by fingerprint) are skipped so a project is stored once.
  const handleMergeSelectedFromTable = useCallback(
    (selected: ProjectGridRow[]) => {
      if (!selected.length) {
        return;
      }

      const seenFingerprints = new Set(
        mergedRows.map((row) => createProjectGridFingerprint(stripProjectGridItem(row))),
      );
      const rowsToAppend: ProjectGridRow[] = [];
      selected.forEach((row) => {
        const fingerprint = createProjectGridFingerprint(row);
        if (seenFingerprints.has(fingerprint)) {
          return;
        }
        seenFingerprints.add(fingerprint);
        rowsToAppend.push(row);
      });

      if (!rowsToAppend.length) {
        setBuilderMessage('Those rows are already in your saved results.');
        return;
      }

      mergeSequence.current += 1;
      setMergedRows((current) => [
        ...current,
        ...createProjectGridItems(rowsToAppend, `merged-${mergeSequence.current}`),
      ]);
      setMergedRowsUndo(null);
      setBuilderMessage(`${rowsToAppend.length} row${rowsToAppend.length === 1 ? '' : 's'} saved into merged results.`);
    },
    [mergedRows],
  );

  const handleDeleteMergedRow = (row: ProjectGridItem) => {
    setMergedRowsUndo(mergedRows);
    setMergedRows((current) => current.filter((item) => item.__key !== row.__key));
    setBuilderMessage('Project removed from merged results.');
  };

  const handleDeleteMergedRows = (rowsToRemove: ProjectGridItem[]) => {
    if (!rowsToRemove.length) {
      return;
    }
    const removeKeys = new Set(rowsToRemove.map((row) => row.__key));
    setMergedRowsUndo(mergedRows);
    setMergedRows((current) => current.filter((item) => !removeKeys.has(item.__key)));
    setBuilderMessage(
      `${rowsToRemove.length} project${rowsToRemove.length === 1 ? '' : 's'} removed from merged results.`,
    );
  };

  const handleUndoMergedRows = () => {
    if (!mergedRowsUndo) {
      return;
    }

    setMergedRows(mergedRowsUndo);
    setMergedRowsUndo(null);
    setBuilderMessage('Merged results restored.');
  };

  const handleResetMergedRows = () => {
    if (!mergedRows.length) {
      return;
    }

    setMergedRowsUndo(mergedRows);
    setMergedRows([]);
    setBuilderMessage('Merged results reset. Undo Merged Change can restore them until you leave this page.');
  };

  return (
    <div className="past-projects-builder">
      {mergedRows.length > 0 || mergedRowsUndo ? (
        <MergedResultsTable
          rows={mergedRows}
          onCreateShare={handleCreateShare}
          onDeleteRow={handleDeleteMergedRow}
          onDeleteRows={handleDeleteMergedRows}
          canUndoRows={Boolean(mergedRowsUndo)}
          onUndoRows={handleUndoMergedRows}
          onResetRows={handleResetMergedRows}
        />
      ) : null}

      <PastProjectsActionBar
        builderMessage={builderMessage}
        error={error}
        loading={loading}
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
                description={
                  isAISearchTable
                    ? 'Use AI to load matching past projects into this table, then select rows to save.'
                    : undefined
                }
                emptyMessage={
                  isAISearchTable
                    ? 'Run AI search to load projects into this table.'
                    : undefined
                }
                initialRows={table.initialRows ?? rows}
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
                onMergeSelected={handleMergeSelectedFromTable}
              />
            );
          })}

          {!searchTables.length ? (
            <div className="project-grid-card project-grid-empty-shell">
              <div className="project-grid-empty">
                No search tables are open. Add a new table to start filtering past projects.
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
