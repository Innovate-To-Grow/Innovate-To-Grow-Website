import {useCallback, useEffect, useId, useMemo, useState} from 'react';
import {useAuth} from '@/features/auth';
import {AISearchLoginDialog} from '../search/AISearchLoginDialog';
import {PastProjectsActionBar} from '../search/PastProjectsActionBar';
import {MERGED_RESULTS_ID, scrollToMergedResults, useKeepScrollAnchor} from '../selection/scrollAnchor';
import {useCurationDraft} from '../draft/useCurationDraft';
import {useDraftHandover} from '../draft/useDraftHandover';
import {useSaveSelectedRows} from '../selection/useSaveSelectedRows';
import {ArchiveLoadFailed} from '../../search/cards/ArchiveLoadFailed';
import {SearchTableStack, type SharedCardProps} from '../../search/cards/SearchTableStack';
import {useSearchTables} from '../../search/state/useSearchTables';
import {MergedResultsTable, type PastProjectShareCreationResult} from '../../merged/composition/MergedResultsTable';
import type {ListMessage} from '../../merged/list/useMergedList';
import {createProjectGridRowMatcher, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import {pluralize} from '../../shared/utils/saveResults';
import {askPartnerPageToScroll} from '../../shared/utils/partnerFrame';

const TABLE_ID_PREFIX = 'search-table';
// What the handed-over projects are added as, in place of a search table's id.
const HANDOVER_SOURCE_ID = 'widget-handover';

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
 * Wraps the parent's share creator so a *successful* share takes its rows out of the draft — the curation
 * now owns them, and returning to the builder should not offer them again. Rows a narrowed search left out
 * of the curation stay in the draft. A failed attempt keeps the draft whole so the user does not lose their
 * rows. While a curation is being saved, adding waits: the curation is made from the rows shown at the
 * click, and those leave the draft once it exists.
 */
function useDraftShareCreation(onCreateShare: CreateShare, dropShared: (rows: ProjectGridRow[]) => void) {
    const [isCreatingShare, setIsCreatingShare] = useState(false);
    const handleCreateShare = useCallback(
        async (shareRows: ProjectGridRow[], name: string, note: string) => {
            setIsCreatingShare(true);
            try {
                const result = await onCreateShare(shareRows, name, note);
                dropShared(shareRows);
                return result;
            } finally {
                setIsCreatingShare(false);
            }
        },
        [dropShared, onCreateShare],
    );
    return {isCreatingShare, handleCreateShare};
}

interface WidgetHandoverOptions {
    rows: ProjectGridRow[];
    loading: boolean;
    addRows: ReturnType<typeof useSaveSelectedRows>['handleMergeSelected'];
    /** Reports in the draft card, which shows once rows were added. */
    reportDraftChange: (text: string) => void;
    /** Reports under the Search Tables heading, when no draft card may be there to say it. */
    reportElsewhere: (text: string) => void;
}

/**
 * Adds the projects a Past Projects widget on a partner's page handed over (see draftHandover.ts) to this draft,
 * loading their details as Add to Curation does, and says what happened.
 */
function useWidgetHandover({rows, loading, addRows, reportDraftChange, reportElsewhere}: WidgetHandoverOptions) {
    useDraftHandover({
        rows,
        loading,
        onHandover: (found, missing) => {
            const missingNote = missing
                ? `${pluralize(missing, 'project')} from the Past Projects widget ${missing === 1 ? 'is' : 'are'} no longer in the archive.`
                : '';
            if (!found.length) {
                reportElsewhere(missingNote);
                return;
            }
            Promise.resolve(addRows(found, {tableId: HANDOVER_SOURCE_ID, reportProgress: () => {}})).then(
                (result) => reportDraftChange(`From the Past Projects widget: ${result.message} ${missingNote}`.trim()),
                () => reportElsewhere('The projects from the Past Projects widget could not be added to the curation draft.'),
            );
        },
    });
}

interface BuilderSavedResultsProps {
    draft: ReturnType<typeof useCurationDraft>;
    pendingSaveCount: number;
    message: ListMessage | null;
    onCreateShare: CreateShare;
}

/** The draft's merged list at the top of the page. */
const BuilderSavedResults = ({draft, pendingSaveCount, message, onCreateShare}: BuilderSavedResultsProps) => (
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
const BuilderSearchSection = ({
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

            {/* Holds about the first table's room (see searchTables.css), so nothing below it moves in when the
                archive arrives. */}
            {loading ? (
                <p className="project-grid-state past-projects-builder-loading" role="status">
                    Loading past projects...
                </p>
            ) : null}
            {archiveUnavailable ? <ArchiveLoadFailed onRetry={onRefreshRows}/> : null}

            {!loading && !archiveUnavailable ? (
                <SearchTableStack
                    tables={tables}
                    idPrefix={TABLE_ID_PREFIX}
                    rows={rows}
                    initialSearch={initialSearch}
                    isAuthenticated={isAuthenticated}
                    canRefresh={Boolean(onRefreshRows)}
                    cardProps={cardProps}
                    copy={{
                        aiDescription:
                            'Use AI to load matching past projects into this table, then check the projects you want and click Add to Curation.',
                        noTablesMessage:
                            'No search tables are open. Add a new table to start searching past projects.',
                    }}
                />
            ) : null}
        </section>
    );
};

/**
 * The past-projects builder: search tables whose checked rows are saved into one merged list, which is a
 * draft (kept in localStorage) until it is saved as a curation. State lives in `builder/draft/useCurationDraft`,
 * `search/state/useSearchTables` and `builder/selection/useSaveSelectedRows`.
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
    // What the search tables did, under their heading; what happened to the draft, in the draft's own card.
    const [tablesMessage, setTablesMessage] = useState('');
    const [draftMessage, setDraftMessage] = useState<ListMessage | null>(null);
    const reportDraftChange = useCallback((text: string) => setDraftMessage({text}), []);

    const draft = useCurationDraft(reportDraftChange);
    // Keep the table that was saved from where it was on screen while the saved results change above it.
    const scrollAnchorRef = useKeepScrollAnchor(draft.mergedRows);
    // In the partner widget, finds out whether the partner page scrolls for it when asked (see partnerFrame.ts).
    useEffect(askPartnerPageToScroll, []);
    const tables = useSearchTables({
        idPrefix: TABLE_ID_PREFIX,
        isAuthenticated,
        rows,
        rowsError: error,
        onRefreshRows,
        onMessage: setTablesMessage,
        refreshingMessage: 'Refreshing this search table from the latest past-project archive...',
    });
    const saving = useSaveSelectedRows({draft, scrollAnchorRef, onMessage: reportDraftChange});
    useWidgetHandover({
        rows,
        loading,
        addRows: saving.handleMergeSelected,
        reportDraftChange,
        reportElsewhere: setTablesMessage,
    });

    const {isCreatingShare, handleCreateShare} = useDraftShareCreation(onCreateShare, draft.dropShared);

    // Lets a search table mark the projects that are already saved.
    const isRowSaved = useMemo(() => createProjectGridRowMatcher(draft.mergedRows).has, [draft.mergedRows]);
    const showSavedResults = draft.mergedRows.length > 0 || draft.canUndo;
    // A card shown again later starts with an empty status line, not with what it said before it went.
    if (!showSavedResults && draftMessage) {
        setDraftMessage(null);
    }

    return (
        <div className="past-projects-builder">
            {showSavedResults ? (
                <BuilderSavedResults
                    draft={draft}
                    pendingSaveCount={saving.savesInFlight}
                    message={draftMessage}
                    onCreateShare={handleCreateShare}
                />
            ) : null}

            <BuilderSearchSection
                tables={tables}
                tablesMessage={tablesMessage}
                rows={rows}
                loading={loading}
                error={error}
                initialSearch={initialSearch}
                isAuthenticated={isAuthenticated}
                draftRows={draft.mergedRows}
                cardProps={{
                    mergeDisabled: isCreatingShare,
                    isRowSaved,
                    savedRowLabel: 'Added',
                    onViewMergedResults: scrollToMergedResults,
                    onSelectionChange: saving.handleSelectionChange,
                    onMergeSelected: saving.handleMergeSelected,
                }}
                onRefreshRows={onRefreshRows}
            />
        </div>
    );
};
