import {useCallback, useEffect, useMemo, useState} from 'react';
import {
    PROJECT_REQUEST_TIMEOUT_MS,
    compactProjectToGridRow,
    fetchAllPastProjectArchive,
    fetchPastProjectShare,
    scheduleProjectToGridRow,
    type PastProjectShare,
    type ProjectGridRow,
} from '@/features/projects/api';
import {fetchCurrentSchedule, type EventSchedulePayload} from '@/features/events/api';
import {getPredominantTerm} from '../components/grid/contracts/projectGrid';

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
 * What a project list says when its rows could not be loaded. The request's own message ("Network Error",
 * "Request failed with status code 503") means nothing to a visitor.
 */
export const PROJECT_LIST_LOAD_ERROR = "We couldn't load the projects. Check your connection and try again.";

const responseStatus = (error: unknown) => (error as {response?: {status?: number}} | null)?.response?.status;

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
    const rows = payload.projects.map((project) => {
        const row = scheduleProjectToGridRow(project);
        const projectId = slotProjectIds.has(project.id)
            ? slotProjectIds.get(project.id)
            : project.track === 0
              ? project.id
              : null;
        return projectId ? {...row, id: projectId} : row;
    });
    // Teams that are not presenting carry no term of their own: they belong to the schedule's semester, and a
    // search for that term ("Fall 2026") should find them too.
    const term = getPredominantTerm(rows);
    return term ? rows.map((row) => (row.semester_label ? row : {...row, semester_label: term})) : rows;
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
    const status = responseStatus(error);
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

        fetchAllPastProjectArchive({}, controller.signal)
            .then((projects) => {
                if (controller.signal.aborted) return;
                setState({
                    requestKey,
                    rows: projects.map(compactProjectToGridRow),
                    error: null,
                });
            })
            .catch(() => {
                if (controller.signal.aborted) return;
                setState({
                    requestKey,
                    rows: [],
                    error: PROJECT_LIST_LOAD_ERROR,
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
