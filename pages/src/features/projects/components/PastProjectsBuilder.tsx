import {useCallback, useId, useMemo, useState} from 'react';
import {useAuth} from '@/features/auth';
import {AISearchLoginDialog} from './builder/AISearchLoginDialog';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {clearPersistedDraft} from './builder/curationDraftStorage';
import {MERGED_RESULTS_ID, scrollToMergedResults, useKeepScrollAnchor} from './builder/scrollAnchor';
import {useCurationDraft} from './builder/useCurationDraft';
import {useSaveSelectedRows} from './builder/useSaveSelectedRows';
import {SearchTableStack} from './search/SearchTableStack';
import {useSearchTables} from './search/useSearchTables';
import {MergedResultsTable, type PastProjectShareCreationResult} from './MergedResultsTable';
import {createProjectGridRowMatcher, type ProjectGridRow} from './projectGrid';

const TABLE_ID_PREFIX = 'search-table';

interface PastProjectsBuilderProps {
    error: string | null;
    loading: boolean;
    rows: ProjectGridRow[];
    /** Seeds the first search table's search (e.g. from "Search Past Projects for …" on Current Projects). */
    initialSearch?: string;
    onRefreshRows?: () => void;
    onCreateShare: (
        rows: ProjectGridRow[],
        name: string,
        note: string,
    ) => Promise<PastProjectShareCreationResult>;
}

type CreateShare = PastProjectsBuilderProps['onCreateShare'];

/**
 * Wraps the parent's share creator so a *successful* share drops the persisted draft — the share
 * now owns this snapshot, and returning to the builder should start clean. A failed attempt keeps
 * the draft so the user does not lose their merged rows. While a shareable link is being created,
 * saving waits: the link is made from the rows shown at the click, and the draft is dropped once it
 * exists, so rows saved meanwhile would be lost.
 */
function useDraftShareCreation(onCreateShare: CreateShare) {
    const [isCreatingShare, setIsCreatingShare] = useState(false);
    const handleCreateShare = useCallback(
        async (shareRows: ProjectGridRow[], name: string, note: string) => {
            setIsCreatingShare(true);
            try {
                const result = await onCreateShare(shareRows, name, note);
                clearPersistedDraft();
                return result;
            } finally {
                setIsCreatingShare(false);
            }
        },
        [onCreateShare],
    );
    return {isCreatingShare, handleCreateShare};
}

interface BuilderSavedResultsProps {
    draft: ReturnType<typeof useCurationDraft>;
    pendingSaveCount: number;
    onCreateShare: CreateShare;
}

/** The draft's merged list at the top of the page. */
const BuilderSavedResults = ({draft, pendingSaveCount, onCreateShare}: BuilderSavedResultsProps) => (
    <MergedResultsTable
        id={MERGED_RESULTS_ID}
        className="past-projects-saved-results"
        rows={draft.mergedRows}
        recentlyAdded={draft.recentlyAdded}
        pendingSaveCount={pendingSaveCount}
        onCreateShare={onCreateShare}
        nameDraft={draft.nameDraft}
        noteDraft={draft.noteDraft}
        onNameDraftChange={draft.setNameDraft}
        onNoteDraftChange={draft.setNoteDraft}
        onDeleteRow={draft.deleteRow}
        onDeleteRows={draft.deleteRows}
        canUndoRows={draft.canUndo}
        onUndoRows={draft.undo}
        onResetRows={draft.reset}
    />
);

/**
 * The past-projects builder: search tables whose checked rows are saved into one merged list, which is a
 * draft (kept in localStorage) until it is saved as a curation. State lives in `builder/` hooks: the draft
 * (`useCurationDraft`), the search tables (`useSearchTables`) and the save flow (`useSaveSelectedRows`).
 */
export const PastProjectsBuilder = ({
                                        error,
                                        loading,
                                        rows,
                                        initialSearch = '',
                                        onRefreshRows,
                                        onCreateShare,
                                    }: PastProjectsBuilderProps) => {
    const {isAuthenticated} = useAuth();
    const [builderMessage, setBuilderMessage] = useState('');
    const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
    const searchTablesHeadingId = useId();

    const draft = useCurationDraft(setBuilderMessage);
    // Keep the table that was saved from where it was on screen while the saved results change above it.
    const scrollAnchorRef = useKeepScrollAnchor(draft.mergedRows);
    const tables = useSearchTables({
        idPrefix: TABLE_ID_PREFIX,
        isAuthenticated,
        rows,
        onRefreshRows,
        onMessage: setBuilderMessage,
        refreshingMessage: 'Refreshing this search table from the latest past-project archive...',
    });
    const saving = useSaveSelectedRows({draft, scrollAnchorRef, onMessage: setBuilderMessage});

    const {isCreatingShare, handleCreateShare} = useDraftShareCreation(onCreateShare);

    const handleAddAISearchTable = () => {
        if (!tables.addAISearchTable()) {
            setIsAISearchLoginDialogOpen(true);
        }
    };

    // Lets a search table mark the projects that are already saved.
    const isRowSaved = useMemo(() => createProjectGridRowMatcher(draft.mergedRows).has, [draft.mergedRows]);

    return (
        <div className="past-projects-builder">
            {draft.mergedRows.length > 0 || draft.canUndo ? (
                <BuilderSavedResults
                    draft={draft}
                    pendingSaveCount={saving.savesInFlight}
                    onCreateShare={handleCreateShare}
                />
            ) : null}

            <section className="past-projects-search-tables" aria-labelledby={searchTablesHeadingId}>
                <PastProjectsActionBar
                    headingId={searchTablesHeadingId}
                    builderMessage={builderMessage}
                    error={error}
                    loading={loading}
                    aiSearchDisabled={tables.hasAISearchTable}
                    aiSearchLoginRequired={!isAuthenticated}
                    onAddAISearchTable={handleAddAISearchTable}
                    onAddSearchTable={tables.addSearchTable}
                />

                {isAISearchLoginDialogOpen ? (
                    <AISearchLoginDialog onClose={() => setIsAISearchLoginDialogOpen(false)}/>
                ) : null}

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
                        rows={rows}
                        initialSearch={initialSearch}
                        isAuthenticated={isAuthenticated}
                        canRefresh={Boolean(onRefreshRows)}
                        cardProps={{
                            mergeDisabled: isCreatingShare,
                            isRowSaved,
                            onViewMergedResults: scrollToMergedResults,
                            onSelectionChange: saving.handleSelectionChange,
                            onMergeSelected: saving.handleMergeSelected,
                        }}
                        copy={{
                            aiDescription:
                                'Use AI to load matching past projects into this table, then check the projects you want and click Save Selected.',
                            noTablesMessage:
                                'No search tables are open. Add a new table to start searching past projects.',
                        }}
                    />
                ) : null}
            </section>
        </div>
    );
};
