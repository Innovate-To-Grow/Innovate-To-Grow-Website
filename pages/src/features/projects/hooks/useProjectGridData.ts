import {useCallback, useEffect, useMemo, useState} from 'react';
import {
    PROJECT_REQUEST_TIMEOUT_MS,
    fetchPastProjectShare,
    scheduleProjectToGridRow,
    type PastProjectShare,
    type ProjectGridRow,
} from '@/features/projects/api';
import {fetchCurrentSchedule, type EventSchedulePayload} from '@/features/events/api';
import {ALL_PROJECTS_CATALOG, PAST_PROJECTS_CATALOG} from '../catalog/catalogs';
import {getPredominantTerm} from '../components/grid/contracts/projectGrid';
import {PROJECT_LIST_LOAD_ERROR, useRevalidatingRows, type RevalidatingRowsResult} from './useRevalidatingRows';

export {PROJECT_LIST_LOAD_ERROR} from './useRevalidatingRows';

type ProjectGridDataResult = RevalidatingRowsResult;

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

interface CurrentProjectGridState {
    requestKey: symbol | null;
    rows: ProjectGridRow[];
    error: string | null;
    classLabels: Record<string, string>;
}

const EMPTY_CLASS_LABELS: Record<string, string> = {};

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

/**
 * The share state, with `seed` put in it as the answer to `requestKey` when it is the share at `shareId`, once per
 * seed. Set while rendering, so the seed is there on the first render and the load never requests it (see
 * https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes).
 */
function useSeededShareState(shareId: string | undefined, requestKey: symbol | null, seed: PastProjectShare | null) {
    const [state, setState] = useState<PastProjectShareState>({
        requestKey: null,
        share: null,
        error: null,
        notFound: false,
    });
    const [usedSeed, setUsedSeed] = useState<PastProjectShare | null>(null);
    if (requestKey && seed?.id === shareId && seed !== usedSeed) {
        setUsedSeed(seed);
        setState({requestKey, share: seed, error: null, notFound: false});
    }
    return [state, setState] as const;
}

/**
 * The share at `shareId`. A `seed` is a share the caller already holds (the one a save just created): when it is the
 * share at `shareId` it stands in for loading it, so the page shows it without asking the server again. Each seed
 * stands in once; Try again (`retry`) loads the share from the server.
 */
export function usePastProjectShareData(
    shareId: string | undefined,
    seed: PastProjectShare | null = null,
): PastProjectShareResult {
    const [attempt, setAttempt] = useState(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- attempt forces a new Symbol so retry() loads again
    const requestKey = useMemo(() => (shareId ? Symbol(shareId) : null), [shareId, attempt]);
    const [state, setState] = useSeededShareState(shareId, requestKey, seed);

    const retry = useCallback(() => setAttempt((count) => count + 1), []);
    const hasResolved = requestKey !== null && state.requestKey === requestKey;

    useEffect(() => {
        if (!requestKey || !shareId || hasResolved) {
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
    }, [requestKey, shareId, hasResolved, setState]);

    if (!requestKey) {
        return {share: null, loading: false, error: null, notFound: false, retry};
    }

    return {
        share: hasResolved ? state.share : null,
        loading: !hasResolved,
        error: hasResolved ? state.error : null,
        notFound: hasResolved && state.notFound,
        retry,
    };
}
