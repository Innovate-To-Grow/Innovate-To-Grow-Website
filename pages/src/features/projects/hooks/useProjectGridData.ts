import {useCallback, useEffect, useMemo, useState} from 'react';
import {
    compactProjectToGridRow,
    fetchPastProjectArchive,
    fetchPastProjectShare,
    scheduleProjectToGridRow,
    type PastProjectShare,
    type ProjectGridRow,
} from '@/features/projects/api';
import {fetchCurrentSchedule, type EventSchedulePayload} from '@/features/events/api';

interface ProjectGridDataResult {
    rows: ProjectGridRow[];
    loading: boolean;
    error: string | null;
    refetch: () => void;
}

interface CurrentProjectGridDataResult extends ProjectGridDataResult {
    /** Class names by class code ("CAP" -> "Engineering Capstone"), from the schedule's sections. */
    classLabels: Record<string, string>;
}

interface PastProjectShareResult {
    share: PastProjectShare | null;
    loading: boolean;
    error: string | null;
    /** The share does not exist (deleted, or a wrong or incomplete link), as opposed to a failed request. */
    notFound: boolean;
    /** Loads the share again after a failed request. */
    retry: () => void;
}

interface ProjectGridRowsState {
    requestKey: symbol | null;
    rows: ProjectGridRow[];
    error: string | null;
}

interface CurrentProjectGridState extends ProjectGridRowsState {
    classLabels: Record<string, string>;
}

const EMPTY_CLASS_LABELS: Record<string, string> = {};

/**
 * The schedule lists presenting teams by their schedule slot (whose id is the slot's, not the project's) and
 * the other teams by project. Each row gets the id of its current-semester project (the slot's `project_id`, or
 * the row's own id at track 0), which its title links to. Those are event CurrentProject ids, which the archive
 * detail endpoint does not know: /projects/:id reads them back from this same payload (useProjectDetail).
 */
export const currentScheduleToGridRows = (payload: Pick<EventSchedulePayload, 'projects'> & Partial<EventSchedulePayload>) => {
    const slotProjectIds = new Map<string, string | null>();
    (payload.sections ?? []).forEach((section) =>
        (section.tracks ?? []).forEach((track) =>
            (track.slots ?? []).forEach((slot) => slotProjectIds.set(slot.id, slot.project_id ?? null)),
        ),
    );
    return payload.projects.map((project) => {
        const row = scheduleProjectToGridRow(project);
        const projectId = slotProjectIds.has(project.id)
            ? slotProjectIds.get(project.id)
            : project.track === 0
              ? project.id
              : null;
        return projectId ? {...row, id: projectId} : row;
    });
};

export const currentScheduleClassLabels = (payload: Partial<EventSchedulePayload>) => {
    const labels: Record<string, string> = {};
    (payload.sections ?? []).forEach((section) => {
        if (section.code && section.label) labels[section.code] = section.label;
    });
    return labels;
};

interface PastProjectShareState {
    requestKey: symbol | null;
    share: PastProjectShare | null;
    error: string | null;
    notFound: boolean;
}

/** A share id the API does not know (404), or one it cannot parse (400): the link itself is wrong. */
const isMissingShareError = (error: unknown) => {
    const status = (error as {response?: {status?: number}} | null)?.response?.status;
    return status === 404 || status === 400;
};

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

        let cancelled = false;

        fetchCurrentSchedule()
            .then((payload) => {
                if (cancelled) return;
                setState({
                    requestKey,
                    rows: currentScheduleToGridRows(payload),
                    error: null,
                    classLabels: currentScheduleClassLabels(payload),
                });
            })
            .catch((err) => {
                if (cancelled) return;
                setState({
                    requestKey,
                    rows: [],
                    error: err instanceof Error ? err.message : 'Failed to load current projects',
                    classLabels: EMPTY_CLASS_LABELS,
                });
            });

        return () => {
            cancelled = true;
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

export function usePastProjectGridData(enabled: boolean = true): ProjectGridDataResult {
    const [refetchCount, setRefetchCount] = useState(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetchCount forces a new Symbol to trigger the fetch useEffect
    const requestKey = useMemo(() => (enabled ? Symbol('past-project-grid') : null), [enabled, refetchCount]);
    const [state, setState] = useState<ProjectGridRowsState>({
        requestKey: null,
        rows: [],
        error: null,
    });

    const refetch = useCallback(() => setRefetchCount((c) => c + 1), []);

    useEffect(() => {
        if (!requestKey) {
            return;
        }

        const controller = new AbortController();
        const loadArchive = async () => {
            const rows: ProjectGridRow[] = [];
            let page = 1;
            while (true) {
                const payload = await fetchPastProjectArchive({page, page_size: 100}, controller.signal);
                rows.push(...payload.results.map(compactProjectToGridRow));
                if (rows.length >= payload.count) break;
                page += 1;
            }
            return rows;
        };

        loadArchive()
            .then((projects) => {
                if (controller.signal.aborted) return;
                setState({
                    requestKey,
                    rows: projects,
                    error: null,
                });
            })
            .catch((err) => {
                if (controller.signal.aborted) return;
                setState({
                    requestKey,
                    rows: [],
                    error: err instanceof Error ? err.message : 'Failed to load past projects',
                });
            });

        return () => {
            controller.abort();
        };
    }, [requestKey]);

    if (!requestKey) {
        return {rows: [], loading: false, error: null, refetch};
    }

    // Stale-while-revalidate: a refetch() keeps serving the previously resolved rows (loading stays
    // false) until the new response lands, so consumers keep their search tables mounted — and their
    // per-table curation intact — across a refresh. Only the very first load reports loading.
    const hasResolved = state.requestKey === requestKey;
    const hasEverResolved = state.requestKey !== null;
    return {
        rows: state.rows,
        loading: !hasResolved && !hasEverResolved,
        error: hasResolved ? state.error : null,
        refetch,
    };
}

export function usePastProjectShareData(shareId: string | undefined): PastProjectShareResult {
    const [attempt, setAttempt] = useState(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- attempt forces a new Symbol so retry() loads again
    const requestKey = useMemo(() => (shareId ? Symbol(shareId) : null), [shareId, attempt]);
    const [state, setState] = useState<PastProjectShareState>({
        requestKey: null,
        share: null,
        error: null,
        notFound: false,
    });

    const retry = useCallback(() => setAttempt((count) => count + 1), []);

    useEffect(() => {
        if (!requestKey || !shareId) {
            return;
        }

        let cancelled = false;

        fetchPastProjectShare(shareId)
            .then((result) => {
                if (cancelled) return;
                setState({
                    requestKey,
                    share: result,
                    error: null,
                    notFound: false,
                });
            })
            .catch((err) => {
                if (cancelled) return;
                setState({
                    requestKey,
                    share: null,
                    error: err instanceof Error ? err.message : 'Failed to load shared past projects',
                    notFound: isMissingShareError(err),
                });
            });

        return () => {
            cancelled = true;
        };
    }, [requestKey, shareId]);

    if (!requestKey) {
        return {share: null, loading: false, error: null, notFound: false, retry};
    }

    const hasResolved = state.requestKey === requestKey;
    return {
        share: hasResolved ? state.share : null,
        loading: !hasResolved,
        error: hasResolved ? state.error : null,
        notFound: hasResolved && state.notFound,
        retry,
    };
}
