import {useCallback, useEffect, useMemo, useState} from 'react';
import {PROJECT_REQUEST_TIMEOUT_MS, type ProjectGridRow} from '@/features/projects/api';
import {fetchCurrentSchedule} from '@/features/events/api';
import {ALL_PROJECTS_CATALOG, PAST_PROJECTS_CATALOG} from '../../catalog/catalogs';
import {PROJECT_LIST_LOAD_ERROR, useRevalidatingRows, type RevalidatingRowsResult} from '../useRevalidatingRows';
import {currentScheduleClassLabels, currentScheduleToGridRows} from './currentProjectGridRows';
import {responseStatus} from './pastProjectShare';

export {PROJECT_LIST_LOAD_ERROR} from '../useRevalidatingRows';

type ProjectGridDataResult = RevalidatingRowsResult;

interface CurrentProjectGridDataResult extends ProjectGridDataResult {
    /** Class names by class code ("CAP" -> "Engineering Capstone"), from the schedule's sections. */
    classLabels: Record<string, string>;
}

interface CurrentProjectGridState {
    requestKey: symbol | null;
    rows: ProjectGridRow[];
    error: string | null;
    classLabels: Record<string, string>;
}

const EMPTY_CLASS_LABELS: Record<string, string> = {};

export function useCurrentProjectGridData(enabled: boolean = true): CurrentProjectGridDataResult {
    const [refetchCount, setRefetchCount] = useState(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetchCount forces a new Symbol to trigger the fetch useEffect
    const requestKey = useMemo(() => (enabled ? Symbol('current-project-grid') : null), [enabled, refetchCount]);
    const [state, setState] = useState<CurrentProjectGridState>({
        requestKey: null,
        rows: [],
        error: null,
        classLabels: EMPTY_CLASS_LABELS,
    });

    const refetch = useCallback(() => setRefetchCount((c) => c + 1), []);

    useEffect(() => {
        if (!requestKey) {
            return;
        }

        const controller = new AbortController();

        fetchCurrentSchedule(null, {signal: controller.signal, timeout: PROJECT_REQUEST_TIMEOUT_MS})
            .then((payload) => {
                if (controller.signal.aborted) return;
                setState({
                    requestKey,
                    rows: currentScheduleToGridRows(payload),
                    error: null,
                    classLabels: currentScheduleClassLabels(payload),
                });
            })
            .catch((err) => {
                if (controller.signal.aborted) return;
                setState({
                    requestKey,
                    rows: [],
                    // A 404 means no schedule is published (or it has no sections yet): there are no current
                    // projects, which the list's empty message says.
                    error: responseStatus(err) === 404 ? null : PROJECT_LIST_LOAD_ERROR,
                    classLabels: EMPTY_CLASS_LABELS,
                });
            });

        return () => {
            controller.abort();
        };
    }, [requestKey]);

    if (!requestKey) {
        return {rows: [], loading: false, error: null, refetch, classLabels: EMPTY_CLASS_LABELS};
    }

    const hasResolved = state.requestKey === requestKey;
    return {
        rows: hasResolved ? state.rows : [],
        loading: !hasResolved,
        error: hasResolved ? state.error : null,
        refetch,
        classLabels: hasResolved ? state.classLabels : EMPTY_CLASS_LABELS,
    };
}

/** The published archive, as the Past Projects builder searches it (useRevalidatingRows: stale while revalidating). */
export function usePastProjectGridData(enabled: boolean = true): ProjectGridDataResult {
    return useRevalidatingRows(PAST_PROJECTS_CATALOG.loadRows, enabled);
}

/**
 * Every project, the active schedule's that are not archived yet and then the archive, as the All Projects builder
 * searches it and a share's owner adds to it.
 */
export function useAllProjectGridData(enabled: boolean = true): ProjectGridDataResult {
    return useRevalidatingRows(ALL_PROJECTS_CATALOG.loadRows, enabled);
}

// Re-exported so this module keeps its public surface.
export {currentScheduleClassLabels, currentScheduleToGridRows} from './currentProjectGridRows';
export {usePastProjectShareData} from './pastProjectShare';
