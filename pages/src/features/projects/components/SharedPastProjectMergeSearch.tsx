import {useCallback, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {buildLoginPath} from '@/features/auth/api/redirects';
import {searchPastProjectsWithAI, toProjectGridRow} from '@/features/projects/api';
import {PastProjectsAIStatus} from './builder/PastProjectsAIStatus';
import {PastProjectsAISearchForm} from './builder/PastProjectsAISearchForm';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {SearchTableCard, type SearchTableHandle} from './SearchTableCard';
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

const getAISearchErrorMessage = (error: unknown) => {
  const payload = (error as {response?: {data?: {detail?: string; message?: string}}}).response?.data;
  return payload?.detail || payload?.message || 'AI search is unavailable right now. Please try again.';
};

interface SharedPastProjectMergeSearchProps {
  currentRows: ProjectGridRow[];
  error: string | null;
  loading: boolean;
  rows: ProjectGridRow[];
  onAddRows: (rows: ProjectGridRow[]) => Promise<void>;
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
}: SharedPastProjectMergeSearchProps) => {
  const {isAuthenticated} = useAuth();
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
  const [selectionState, setSelectionState] = useState<Record<string, boolean>>({});
  const [builderMessage, setBuilderMessage] = useState('');
  const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
  const [isMergeDialogOpen, setIsMergeDialogOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const tableSequence = useRef(1);
  const tableRefs = useRef<Record<string, SearchTableHandle | null>>({});

  const currentFingerprints = useMemo(
    () => new Set(currentRows.map((row) => createProjectGridFingerprint(row))),
    [currentRows],
  );
  const availableRows = useMemo(
    () => rows.filter((row) => !currentFingerprints.has(createProjectGridFingerprint(row))),
    [currentFingerprints, rows],
  );
  const hasAnySelection = Object.values(selectionState).some(Boolean);
  const hasAISearchTable = searchTables.some((table) => table.type === 'ai');
  const standardSearchTableIds = searchTables.filter((table) => table.type === 'standard').map((table) => table.id);
  const standardSearchTableCount = standardSearchTableIds.length;

  const handleSelectionStateChange = useCallback((tableId: string, hasSelection: boolean) => {
    setSelectionState((current) => {
      if (current[tableId] === hasSelection) return current;
      return {...current, [tableId]: hasSelection};
    });
  }, []);

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
        .filter((row) => !currentFingerprints.has(createProjectGridFingerprint(row)));

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
    setSelectionState((current) => {
      const next = {...current};
      delete next[tableId];
      return next;
    });
    delete tableRefs.current[tableId];
  };

  const applyToSearchTables = (action: (table: SearchTableHandle) => void) => {
    searchTables.forEach(({id}) => {
      const table = tableRefs.current[id];
      if (table) {
        action(table);
      }
    });
  };

  const handleMergeResults = () => {
    if (!searchTables.length) {
      return;
    }
    if (!hasAnySelection) {
      setBuilderMessage('Select the projects you want to add, then choose Add Selected Projects.');
      return;
    }
    setIsMergeDialogOpen(true);
  };

  const handleConfirmMergeResults = async () => {
    if (!searchTables.length || !hasAnySelection) {
      setIsMergeDialogOpen(false);
      return;
    }

    const seenFingerprints = new Set(currentFingerprints);
    const rowsToAppend: ProjectGridRow[] = [];

    searchTables.forEach(({id}) => {
      const table = tableRefs.current[id];
      if (!table) {
        return;
      }
      table.getSelectedRows().forEach((row) => {
        const fingerprint = createProjectGridFingerprint(row);
        if (seenFingerprints.has(fingerprint)) {
          return;
        }
        seenFingerprints.add(fingerprint);
        rowsToAppend.push(row);
      });
    });

    if (!rowsToAppend.length) {
      setBuilderMessage('Those projects are already in this shared result.');
      setIsMergeDialogOpen(false);
      return;
    }

    setIsSaving(true);
    setBuilderMessage('');
    try {
      await onAddRows(rowsToAppend);
      setBuilderMessage(`${rowsToAppend.length} project${rowsToAppend.length === 1 ? '' : 's'} added.`);
      searchTables.forEach(({id}) => {
        delete tableRefs.current[id];
      });
      setSearchTables([]);
      setSelectionState({});
      setIsMergeDialogOpen(false);
    } catch {
      setBuilderMessage('Unable to add selected projects. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="shared-past-project-merge-search">
      <PastProjectsActionBar
        builderMessage={builderMessage}
        error={error}
        hasAnySelection={hasAnySelection}
        loading={loading || isSaving}
        mergeButtonLabel="Add Selected Projects"
        searchTableCount={searchTables.length}
        title="Add Projects"
        aiSearchDisabled={hasAISearchTable}
        aiSearchLoginRequired={!isAuthenticated}
        onAddAISearchTable={handleAddAISearchTable}
        onAddSearchTable={handleAddSearchTable}
        onMergeResults={handleMergeResults}
        onDeleteSelectedRows={() => applyToSearchTables((table) => table.deleteSelectedRows())}
        onKeepSelectedRows={() => applyToSearchTables((table) => table.keepSelectedRows())}
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

      {isMergeDialogOpen ? (
        <PastProjectsDialog
          title="Add selected projects?"
          confirmLabel={isSaving ? 'Adding...' : 'Add Projects'}
          onCancel={() => setIsMergeDialogOpen(false)}
          onConfirm={() => void handleConfirmMergeResults()}
        >
          <p>Add the checked rows from the search tables into this shared past project result.</p>
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
                ref={(instance) => {
                  tableRefs.current[table.id] = instance;
                }}
                canRemove={searchTables.length > 1}
                description={
                  isAISearchTable
                    ? 'Use AI to load matching past projects into this table, then select rows to add.'
                    : undefined
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
                onSelectionStateChange={handleSelectionStateChange}
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
