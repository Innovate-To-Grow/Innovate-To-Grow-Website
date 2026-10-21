import {useId, useMemo, useState} from 'react';
import {useAuth} from '@/features/auth';
import {AISearchLoginDialog} from './builder/AISearchLoginDialog';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {createProjectGridRowMatcher, type ProjectGridRow} from './projectGrid';
import {SearchTableStack} from './search/SearchTableStack';
import {useSearchTables} from './search/useSearchTables';
import {useAddToShare} from './shared/useAddToShare';

const TABLE_ID_PREFIX = 'shared-search-table';

interface SharedPastProjectMergeSearchProps {
  currentRows: ProjectGridRow[];
  error: string | null;
  loading: boolean;
  rows: ProjectGridRow[];
  /** Adds the rows to the share; may resolve to how many were actually appended (others were already there). */
  onAddRows: (rows: ProjectGridRow[]) => Promise<number | void>;
  onRefreshRows?: () => void;
}

/** On a shared page its owner can edit: search the full archive and add more projects to it. */
export const SharedPastProjectMergeSearch = ({
  currentRows,
  error,
  loading,
  rows,
  onAddRows,
  onRefreshRows,
}: SharedPastProjectMergeSearchProps) => {
  const {isAuthenticated} = useAuth();
  const headingId = useId();
  const [builderMessage, setBuilderMessage] = useState('');
  const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);

  // Matches on project id as well as content: a compact archive row never has the fingerprint of the hydrated
  // copy of the same project already in this share, which would otherwise be offered (and added) again.
  const isAlreadyShared = useMemo(() => createProjectGridRowMatcher(currentRows).has, [currentRows]);
  const availableRows = useMemo(() => rows.filter((row) => !isAlreadyShared(row)), [isAlreadyShared, rows]);
  const tables = useSearchTables({
    idPrefix: TABLE_ID_PREFIX,
    isAuthenticated,
    rows,
    onRefreshRows,
    onMessage: setBuilderMessage,
    filterAIRows: (aiRows) => aiRows.filter((row) => !isAlreadyShared(row)),
    allAIRowsFilteredMessage: 'AI found projects that are already in this shared result.',
    refreshingMessage: 'Refreshing this full-archive search table from the latest past-project data...',
  });
  const {isSaving, addSelected} = useAddToShare({currentRows, isAlreadyShared, onAddRows, onMessage: setBuilderMessage});

  return (
    <section className="shared-past-project-merge-search past-projects-search-tables" aria-labelledby={headingId}>
      <PastProjectsActionBar
        headingId={headingId}
        builderMessage={builderMessage}
        error={error}
        loading={loading || isSaving}
        title="Add Projects from Full Archive"
        saveLabel="Add Selected"
        saveTarget="this shared page"
        savedLabel="Added"
        aiSearchDisabled={tables.hasAISearchTable}
        aiSearchLoginRequired={!isAuthenticated}
        onAddAISearchTable={() => {
          if (!tables.addAISearchTable()) setIsAISearchLoginDialogOpen(true);
        }}
        onAddSearchTable={tables.addSearchTable}
      />

      {isAISearchLoginDialogOpen ? <AISearchLoginDialog onClose={() => setIsAISearchLoginDialogOpen(false)} /> : null}

      {loading ? <p className="project-grid-state">Loading past projects...</p> : null}
      {error ? (
        <p className="project-grid-state project-grid-state-error itg-error" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && !error ? (
        <SearchTableStack
          tables={tables}
          idPrefix={TABLE_ID_PREFIX}
          rows={availableRows}
          isAuthenticated={isAuthenticated}
          canRefresh={Boolean(onRefreshRows)}
          cardProps={{
            mergeLabel: 'Add Selected',
            mergeVerb: 'Add',
            mergingVerb: 'Adding',
            mergeDisabled: isSaving,
            isRowSaved: isAlreadyShared,
            savedRowLabel: 'Added',
            onMergeSelected: addSelected,
          }}
          copy={{
            aiDescription:
              'Use AI to load matching past projects into this table, then check the projects you want and click Add Selected.',
            standardDescription:
              'Search the full past-project archive for additional projects to add to this shared result.',
            noTablesMessage: 'No search tables are open. Add a new table to search for more projects.',
          }}
        />
      ) : null}
    </section>
  );
};
