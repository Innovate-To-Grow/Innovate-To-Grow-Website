import {useId, useMemo, useState} from 'react';
import {useAuth} from '@/features/auth';
import {AISearchLoginDialog} from '../../builder/search/AISearchLoginDialog';
import {PastProjectsActionBar} from '../../builder/search/PastProjectsActionBar';
import {createProjectGridRowMatcher, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import {ArchiveLoadState} from '../../search/cards/ArchiveLoadState';
import {SearchTableStack} from '../../search/cards/SearchTableStack';
import {useSearchTables} from '../../search/state/useSearchTables';
import {useAddToShare} from './useAddToShare';

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

/**
 * On a shared page its owner can edit: search for more projects and add them to it. It searches the list it is given
 * (every project, on the share page) and words its states and help after the list in context (useProjectCatalog).
 */
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
  // A failed refresh keeps the archive it had (the table that asked reports it); a failed first load has none.
  const archiveUnavailable = Boolean(error) && !rows.length;
  const tables = useSearchTables({
    idPrefix: TABLE_ID_PREFIX,
    isAuthenticated,
    rows,
    rowsError: error,
    onRefreshRows,
    onMessage: setBuilderMessage,
    filterAIRows: (aiRows) => aiRows.filter((row) => !isAlreadyShared(row)),
    allAIRowsFilteredMessage: 'AI found projects that are already in this curation.',
  });
  const {isSaving, addSelected} = useAddToShare({currentRows, isAlreadyShared, onAddRows, onMessage: setBuilderMessage});

  return (
    <section className="shared-past-project-merge-search past-projects-search-tables" aria-labelledby={headingId}>
      <PastProjectsActionBar
        headingId={headingId}
        builderMessage={builderMessage}
        error={archiveUnavailable ? error : null}
        loading={loading || isSaving}
        title="Add More Projects"
        saveLabel="Add Selected"
        saveTarget="this curation"
        savedLabel="Added"
        aiSearchDisabled={tables.hasAISearchTable}
        aiSearchLoginRequired={!isAuthenticated}
        onAddAISearchTable={() => {
          if (!tables.addAISearchTable()) setIsAISearchLoginDialogOpen(true);
        }}
        onAddSearchTable={tables.addSearchTable}
      />

      {isAISearchLoginDialogOpen ? <AISearchLoginDialog onClose={() => setIsAISearchLoginDialogOpen(false)} /> : null}

      <ArchiveLoadState loading={loading} failed={archiveUnavailable} onRetry={onRefreshRows} headingId={headingId} />

      {!loading && !archiveUnavailable ? (
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
              'Use AI to load matching projects into this table, then check the projects you want and click Add Selected.',
            standardDescription: 'Search for more projects to add to this curation.',
            noTablesMessage: 'No search tables are open. Add a new table to search for more projects.',
          }}
        />
      ) : null}
    </section>
  );
};
