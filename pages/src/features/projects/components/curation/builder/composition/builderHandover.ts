import {useCallback, useState} from 'react';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import {useDraftHandover} from '../draft/useDraftHandover';
import {useSaveSelectedRows} from '../selection/useSaveSelectedRows';
import {type PastProjectShareCreationResult} from '../../merged/composition/MergedResultsTable';
import {type ProjectGridRow} from '../../../grid/contracts/projectGrid';

export const TABLE_ID_PREFIX = 'search-table';
// What the handed-over projects are added as, in place of a search table's id.
const HANDOVER_SOURCE_ID = 'widget-handover';

export interface PastProjectsBuilderProps {
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

export type CreateShare = PastProjectsBuilderProps['onCreateShare'];

/**
 * Wraps the parent's share creator so a *successful* share takes its rows out of the draft — the curation
 * now owns them, and returning to the builder should not offer them again. Rows a narrowed search left out
 * of the curation stay in the draft. A failed attempt keeps the draft whole so the user does not lose their
 * rows. While a curation is being saved, adding waits: the curation is made from the rows shown at the
 * click, and those leave the draft once it exists.
 */
export function useDraftShareCreation(onCreateShare: CreateShare, dropShared: (rows: ProjectGridRow[]) => void) {
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
 * Adds the projects a Past Projects (or All Projects) widget on a partner's page handed over (see draftHandover.ts)
 * to this draft, loading their details as Add to Curation does, and says what happened.
 */
export function useWidgetHandover({rows, loading, addRows, reportDraftChange, reportElsewhere}: WidgetHandoverOptions) {
    const {copy} = useProjectCatalog();
    useDraftHandover({
        rows,
        loading,
        onHandover: (found, missing) => {
            const missingNote = missing ? copy.handoverMissing(missing) : '';
            if (!found.length) {
                reportElsewhere(missingNote);
                return;
            }
            Promise.resolve(addRows(found, {tableId: HANDOVER_SOURCE_ID, reportProgress: () => {}})).then(
                (result) => reportDraftChange(`From the ${copy.widgetName}: ${result.message} ${missingNote}`.trim()),
                () =>
                    reportElsewhere(`The projects from the ${copy.widgetName} could not be added to the curation draft.`),
            );
        },
    });
}
