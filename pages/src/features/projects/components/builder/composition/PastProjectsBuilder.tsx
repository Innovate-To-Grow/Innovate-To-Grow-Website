import {useCallback, useEffect, useMemo, useState} from 'react';
import {useAuth} from '@/features/auth';
import {scrollToMergedResults, useKeepScrollAnchor} from '../selection/scrollAnchor';
import {useCurationDraft} from '../draft/useCurationDraft';
import {useSaveSelectedRows} from '../selection/useSaveSelectedRows';
import {useSearchTables} from '../../search/state/useSearchTables';
import type {ListMessage} from '../../merged/list/useMergedList';
import {createProjectGridRowMatcher} from '../../grid/contracts/projectGrid';
import {askPartnerPageToScroll} from '../../shared/utils/partnerFrame';
import {
  type PastProjectsBuilderProps,
  TABLE_ID_PREFIX,
  useDraftShareCreation,
  useWidgetHandover,
} from './builderHandover';
import {BuilderSavedResults, BuilderSearchSection} from './BuilderSections';

/**
 * The past-projects builder: search tables whose checked rows are saved into one merged list, which is a
 * draft (kept in localStorage) until it is saved as a curation. State lives in `builder/draft/useCurationDraft`,
 * `search/state/useSearchTables` and `builder/selection/useSaveSelectedRows`. The list it searches and the words
 * naming it are the page's ProjectCatalog (Past Projects, or All Projects); both pages share the one draft.
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
