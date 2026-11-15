import {useId, useState} from 'react';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import {AISearchLoginDialog} from '../search/AISearchLoginDialog';
import {PastProjectsActionBar} from '../search/PastProjectsActionBar';
import {MERGED_RESULTS_ID} from '../selection/scrollAnchor';
import {useCurationDraft} from '../draft/useCurationDraft';
import {ArchiveLoadState} from '../../../search/cards/ArchiveLoadState';
import {SearchTableStack, type SharedCardProps} from '../../../search/cards/SearchTableStack';
import {useSearchTables} from '../../../search/state/useSearchTables';
import {MergedResultsTable} from '../../merged/composition/MergedResultsTable';
import type {ListMessage} from '../../merged/list/useMergedList';
import {type ProjectGridRow} from '../../../grid/contracts/projectGrid';
import {type CreateShare, TABLE_ID_PREFIX} from './builderHandover';

interface BuilderSavedResultsProps {
    draft: ReturnType<typeof useCurationDraft>;
    pendingSaveCount: number;
    message: ListMessage | null;
    onCreateShare: CreateShare;
}

/** The draft's merged list at the top of the page. */
export const BuilderSavedResults = ({draft, pendingSaveCount, message, onCreateShare}: BuilderSavedResultsProps) => (
    <MergedResultsTable
        id={MERGED_RESULTS_ID}
        className="past-projects-saved-results"
        rows={draft.mergedRows}
        recentlyAdded={draft.recentlyAdded}
        pendingSaveCount={pendingSaveCount}
        message={message}
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

interface BuilderSearchSectionProps {
    tables: ReturnType<typeof useSearchTables>;
    /** What the search tables did (a refresh, …), under their heading. */
    tablesMessage: string;
    rows: ProjectGridRow[];
    loading: boolean;
    error: string | null;
    initialSearch: string;
    isAuthenticated: boolean;
    /** The draft, carried to the full page when AI search asks a widget visitor to sign in. */
    draftRows: ProjectGridRow[];
    cardProps: SharedCardProps;
    onRefreshRows?: () => void;
}

/** The Search Tables section: its action bar, the archive's loading or failure, and the tables. */
export const BuilderSearchSection = ({
                                  tables,
                                  tablesMessage,
                                  rows,
                                  loading,
                                  error,
                                  initialSearch,
                                  isAuthenticated,
                                  draftRows,
                                  cardProps,
                                  onRefreshRows,
                              }: BuilderSearchSectionProps) => {
    const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
    const headingId = useId();
    const {copy} = useProjectCatalog();
    // A failed refresh keeps the archive it had, and the table that asked reports it; only a first load that
    // failed leaves nothing to search.
    const archiveUnavailable = Boolean(error) && !rows.length;

    return (
        <section className="past-projects-search-tables" aria-labelledby={headingId}>
            <PastProjectsActionBar
                headingId={headingId}
                builderMessage={tablesMessage}
                error={archiveUnavailable ? error : null}
                loading={loading}
                aiSearchDisabled={tables.hasAISearchTable}
                aiSearchLoginRequired={!isAuthenticated}
                onAddAISearchTable={() => {
                    if (!tables.addAISearchTable()) {
                        setIsAISearchLoginDialogOpen(true);
                    }
                }}
                onAddSearchTable={tables.addSearchTable}
            />

            {isAISearchLoginDialogOpen ? (
                <AISearchLoginDialog draftRows={draftRows} onClose={() => setIsAISearchLoginDialogOpen(false)}/>
            ) : null}

            {/* While loading, holds about the first table's room (see searchTables.css), so nothing below it moves
                in when the archive arrives. */}
            <ArchiveLoadState
                loading={loading}
                failed={archiveUnavailable}
                onRetry={onRefreshRows}
                headingId={headingId}
                loadingClassName="past-projects-builder-loading"
            />

            {!loading && !archiveUnavailable ? (
                <SearchTableStack
                    tables={tables}
                    idPrefix={TABLE_ID_PREFIX}
                    rows={rows}
                    initialSearch={initialSearch}
                    isAuthenticated={isAuthenticated}
                    canRefresh={Boolean(onRefreshRows)}
                    cardProps={cardProps}
                    copy={{aiDescription: copy.aiDescription, noTablesMessage: copy.noTablesMessage}}
                />
            ) : null}
        </section>
    );
};
