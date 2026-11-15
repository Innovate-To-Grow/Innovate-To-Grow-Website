import {useCallback, useEffect, useMemo, useState} from 'react';
import type {ProjectGridRow} from '@/features/projects/api';

/**
 * What a project list says when its rows could not be loaded. The request's own message ("Network Error",
 * "Request failed with status code 503") means nothing to a visitor. It names no cause: the same words follow a
 * dropped connection, a server error and a timeout.
 */
export const PROJECT_LIST_LOAD_ERROR = "We couldn't load the projects. Please try again.";

/** Loads every row of one project list. Keep it stable (module-level): a new function is a new list. */
export type ProjectRowsLoader = (signal: AbortSignal) => Promise<ProjectGridRow[]>;

export interface RevalidatingRowsResult {
    rows: ProjectGridRow[];
    loading: boolean;
    error: string | null;
    refetch: () => void;
}

interface RevalidatingRowsState {
    requestKey: symbol | null;
    /** The list the rows came from. */
    load: ProjectRowsLoader | null;
    rows: ProjectGridRow[];
    error: string | null;
}

/**
 * The rows `load` resolves to, loaded again on refetch(). Stale-while-revalidate: a refetch keeps serving the rows
 * it has (loading stays false) until the new response lands, so consumers keep their search tables mounted, and
 * their per-table curation intact, across a refresh. A failed refetch reports its error next to the rows it kept.
 * Only a load with no rows to serve meanwhile (the first one, or a retry after it failed) reports loading.
 *
 * The stale rows are served only while `load` is the list they came from: a search table seeds its rows once, so
 * rows of another list (the archive, while every project loads) would otherwise stay in it.
 */
export function useRevalidatingRows(load: ProjectRowsLoader, enabled: boolean = true): RevalidatingRowsResult {
    const [refetchCount, setRefetchCount] = useState(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load and refetchCount force a new Symbol to trigger the fetch useEffect
    const requestKey = useMemo(() => (enabled ? Symbol('project-rows') : null), [enabled, load, refetchCount]);
    const [state, setState] = useState<RevalidatingRowsState>({requestKey: null, load: null, rows: [], error: null});

    const refetch = useCallback(() => setRefetchCount((c) => c + 1), []);

    useEffect(() => {
        if (!requestKey) {
            return;
        }

        const controller = new AbortController();

        load(controller.signal)
            .then((rows) => {
                if (controller.signal.aborted) return;
                setState({requestKey, load, rows, error: null});
            })
            .catch(() => {
                if (controller.signal.aborted) return;
                setState((previous) => ({
                    requestKey,
                    load,
                    rows: previous.load === load ? previous.rows : [],
                    error: PROJECT_LIST_LOAD_ERROR,
                }));
            });

        return () => {
            controller.abort();
        };
    }, [load, requestKey]);

    if (!requestKey) {
        return {rows: [], loading: false, error: null, refetch};
    }

    const hasResolved = state.requestKey === requestKey;
    const rows = state.load === load ? state.rows : [];
    return {
        rows,
        loading: !hasResolved && rows.length === 0,
        error: hasResolved ? state.error : null,
        refetch,
    };
}
