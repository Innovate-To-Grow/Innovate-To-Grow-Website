import {useCallback, useRef, useState} from 'react';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {MergedResultsTable} from './MergedResultsTable';
import {SearchTableCard, type SearchTableHandle} from './SearchTableCard';
import {
  createProjectGridFingerprint,
  createProjectGridItems,
  stripProjectGridItem,
  type ProjectGridItem,
  type ProjectGridRow,
} from './projectGrid';

const INITIAL_SEARCH_TABLE = {id: 'search-table-1', title: 'Search Table 1'};

interface PastProjectsBuilderProps {
  error: string | null;
  loading: boolean;
  rows: ProjectGridRow[];
  onCreateShare: (rows: ProjectGridRow[]) => Promise<string>;
}

interface SearchTableState {
  id: string;
  title: string;
}

export const PastProjectsBuilder = ({
  error,
  loading,
  rows,
  onCreateShare,
}: PastProjectsBuilderProps) => {
  const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
  const [selectionState, setSelectionState] = useState<Record<string, boolean>>({});
  const [deleteMode, setDeleteMode] = useState(false);
  const [mergedRows, setMergedRows] = useState<ProjectGridItem[]>([]);
  const [deletedFingerprints, setDeletedFingerprints] = useState<Set<string>>(new Set());
  const [builderMessage, setBuilderMessage] = useState('');
  const tableSequence = useRef(1);
  const mergeSequence = useRef(0);
  const tableRefs = useRef<Record<string, SearchTableHandle | null>>({});

  const hasAnySelection = Object.values(selectionState).some(Boolean);

  const handleSelectionStateChange = useCallback((tableId: string, hasSelection: boolean) => {
    setSelectionState((current) => {
      if (current[tableId] === hasSelection) return current;
      return {...current, [tableId]: hasSelection};
    });
  }, []);

  const handleAddSearchTable = () => {
    tableSequence.current += 1;
    const id = `search-table-${tableSequence.current}`;
    setSearchTables((current) => [...current, {id, title: `Search Table ${tableSequence.current}`}]);
    setBuilderMessage('');
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

    if (!window.confirm('Merge the filtered rows from all open search tables into saved results?')) {
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
      table.getFilteredRows().forEach((row) => {
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
      setBuilderMessage(`${rowsToAppend.length} row${rowsToAppend.length === 1 ? '' : 's'} merged into saved results.`);
    } else {
      setBuilderMessage('No new rows matched the current filters.');
    }

    searchTables.forEach(({id}) => {
      delete tableRefs.current[id];
    });
    setSearchTables([]);
    setSelectionState({});
    setDeleteMode(false);
  };

  const handleDeleteMergedRow = (row: ProjectGridItem) => {
    const fingerprint = createProjectGridFingerprint(stripProjectGridItem(row));
    setMergedRows((current) => current.filter((item) => item.__key !== row.__key));
    setDeletedFingerprints((current) => new Set([...current, fingerprint]));
  };

  return (
    <div className="past-projects-builder">
      {mergedRows.length > 0 ? (
        <MergedResultsTable rows={mergedRows} onCreateShare={onCreateShare} onDeleteRow={handleDeleteMergedRow} />
      ) : null}

      <PastProjectsActionBar
        builderMessage={builderMessage}
        error={error}
        hasAnySelection={hasAnySelection}
        loading={loading}
        searchTableCount={searchTables.length}
        deleteMode={deleteMode}
        onAddSearchTable={handleAddSearchTable}
        onMergeResults={handleMergeResults}
        onDeleteSelectedRows={() => applyToSearchTables((table) => table.deleteSelectedRows())}
        onKeepSelectedRows={() => applyToSearchTables((table) => table.keepSelectedRows())}
        onDeleteModeChange={setDeleteMode}
      />

      {loading ? <div className="project-grid-card"><div className="project-grid-state">Loading past projects...</div></div> : null}
      {error ? <div className="project-grid-card"><div className="project-grid-state project-grid-state-error">{error}</div></div> : null}

      {!loading && !error ? (
        <div className="search-table-stack">
          {searchTables.map((table) => (
            <SearchTableCard
              key={table.id}
              ref={(instance) => {
                tableRefs.current[table.id] = instance;
              }}
              deleteMode={deleteMode}
              initialRows={rows}
              tableId={table.id}
              title={table.title}
              onRemove={handleRemoveSearchTable}
              onSelectionStateChange={handleSelectionStateChange}
            />
          ))}

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
