import {useCallback, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {searchPastProjectsWithAI, toProjectGridRow} from '@/features/projects/api';
import {PastProjectsAIStatus} from './builder/PastProjectsAIStatus';
import {PastProjectsAISearchForm} from './builder/PastProjectsAISearchForm';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {MergedResultsTable, type PastProjectShareCreationResult} from './MergedResultsTable';
import {SearchTableCard, type SearchTableHandle} from './SearchTableCard';
import {
  createProjectGridFingerprint,
  createProjectGridItems,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

const INITIAL_SEARCH_TABLE: SearchTableState = {id: 'search-table-1', type: 'standard'};

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

interface PastProjectsBuilderProps {
  error: string | null;
  loading: boolean;
  rows: ProjectGridRow[];
  onCreateShare: (
    rows: ProjectGridRow[],
    name: string,
    note: string,
    detailsText: string,
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
  onCreateShare,
}: PastProjectsBuilderProps) => {
  const {isAuthenticated} = useAuth();
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
  const [selectionState, setSelectionState] = useState<Record<string, boolean>>({});
  const [mergedRows, setMergedRows] = useState<ProjectGridItem[]>([]);
  const [deletedFingerprints, setDeletedFingerprints] = useState<Set<string>>(new Set());
  const [builderMessage, setBuilderMessage] = useState('');
  const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
  const [isMergeDialogOpen, setIsMergeDialogOpen] = useState(false);
  const tableSequence = useRef(1);
  const mergeSequence = useRef(0);
  const tableRefs = useRef<Record<string, SearchTableHandle | null>>({});

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

    // Save/Merge stores only the rows the user has explicitly checked. Without a
    // selection there is nothing to save — guide the user instead of silently
    // merging the entire archive (the original bug).
    if (!hasAnySelection) {
      setBuilderMessage('Select the rows you want to save (check their boxes), then choose Save/Merge Results.');
      return;
    }

    setIsMergeDialogOpen(true);
  };

  const handleConfirmMergeResults = () => {
    setIsMergeDialogOpen(false);

    if (!searchTables.length || !hasAnySelection) {
      return;
    }

    const nextMergedRows = [...mergedRows];
    const seenFingerprints = new Set(
      nextMergedRows.map((row) => createProjectGridFingerprint(stripProjectGridItem(row))),
    );

    const rowsToAppend: ProjectGridRow[] = [];

    searchTables.forEach(({id}) => {
      const table = tableRefs.current[id];
      if (!table) {
        return;
      }
      table.getSelectedRows().forEach((row) => {
        const fingerprint = createProjectGridFingerprint(row);
        if (seenFingerprints.has(fingerprint) || deletedFingerprints.has(fingerprint)) {
          return;
        }
        seenFingerprints.add(fingerprint);
        rowsToAppend.push(row);
      });
    });

    if (rowsToAppend.length) {
      mergeSequence.current += 1;
      nextMergedRows.push(...createProjectGridItems(rowsToAppend, `merged-${mergeSequence.current}`));
      setMergedRows(nextMergedRows);
      setBuilderMessage(`${rowsToAppend.length} row${rowsToAppend.length === 1 ? '' : 's'} saved into merged results.`);
    } else {
      setBuilderMessage('Those rows are already in your saved results.');
    }

    searchTables.forEach(({id}) => {
      delete tableRefs.current[id];
    });
    setSearchTables([]);
    setSelectionState({});
  };

  const handleDeleteMergedRow = (row: ProjectGridItem) => {
    const fingerprint = createProjectGridFingerprint(stripProjectGridItem(row));
    setMergedRows((current) => current.filter((item) => item.__key !== row.__key));
    setDeletedFingerprints((current) => new Set([...current, fingerprint]));
  };

  return (
    <div className="past-projects-builder">
      {mergedRows.length > 0 ? (
        <MergedResultsTable
          rows={mergedRows}
          onCreateShare={onCreateShare}
          onDeleteRow={handleDeleteMergedRow}
        />
      ) : null}

      <PastProjectsActionBar
        builderMessage={builderMessage}
        error={error}
        hasAnySelection={hasAnySelection}
        loading={loading}
        searchTableCount={searchTables.length}
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
            window.location.href = '/login';
          }}
        >
          <p>You need to sign in before using AI search.</p>
        </PastProjectsDialog>
      ) : null}

      {isMergeDialogOpen ? (
        <PastProjectsDialog
          title="Save selected rows?"
          confirmLabel="Save Rows"
          onCancel={() => setIsMergeDialogOpen(false)}
          onConfirm={handleConfirmMergeResults}
        >
          <p>
            Save the selected rows from all open search tables into your merged results? Duplicate projects already
            saved will be skipped.
          </p>
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
                    ? 'Use AI to load matching past projects into this table, then select rows to merge.'
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
                onSelectionStateChange={handleSelectionStateChange}
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
