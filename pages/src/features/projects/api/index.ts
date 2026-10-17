import {api} from '@/lib/api';
import {
    authApi,
    getAccessToken,
    isDefinitiveAuthFailure,
} from '@/features/auth';
import {formatSemesterLabel} from '@/lib/format';
import type {PaginatedResponse} from '@/types/api';
import type {ScheduleProjectRow} from '@/features/events/api';

export type {PaginatedResponse} from '@/types/api';

export interface ProjectSummary {
    id: string;
    project_title: string;
    team_name: string;
    organization: string;
    industry: string;
    class_code: string;
}

export interface ProjectTableRow {
    id: string;
    semester_label: string;
    class_code: string;
    team_number: string;
    team_name: string;
    project_title: string;
    organization: string;
    industry: string;
    abstract: string;
    student_names: string;
    is_presenting?: boolean;
    track: number | null;
    presentation_order: number | null;
}

export interface CompactPastProjectRow {
    id: string;
    semester_label: string;
    class_code: string;
    team_number: string;
    team_name: string;
    project_title: string;
    organization: string;
    industry: string;
    track: number | null;
    presentation_order: number | null;
}

export interface PastProjectArchiveQuery {
    page?: number;
    page_size?: number;
    search?: string;
    year?: number;
    season?: 1 | 2;
    semester?: string;
}

export interface ProjectGridRow {
    id?: string;
    semester_label: string;
    class_code: string;
    team_number: string;
    team_name: string;
    project_title: string;
    organization: string;
    industry: string;
    abstract: string;
    student_names: string;
    is_presenting: string;
}

export interface ProjectDetail {
    id: string;
    project_title: string;
    team_name: string;
    team_number: string;
    organization: string;
    industry: string;
    abstract: string;
    student_names: string;
    class_code: string;
    track: number | null;
    presentation_order: number | null;
    semester_label: string;
}

export interface SemesterWithProjects {
    id: string;
    year: number;
    season: number;
    label: string;
    projects: ProjectSummary[];
}

export interface SemesterWithFullProjects {
    id: string;
    year: number;
    season: number;
    label: string;
    projects: ProjectTableRow[];
}

export interface PastProjectShare {
    id: string;
    name: string;
    rows: ProjectGridRow[];
    note: string;
    details_text: string;
    version: number;
    share_url: string;
    can_edit: boolean;
    created_at: string;
}

/**
 * Title of a share saved without a name or any note text of the owner's own. Mirrors the backend
 * default (src/apps/projects/services/share_names.py DEFAULT_SHARE_NAME); also the display fallback for
 * legacy shares stored with a blank name.
 */
export const DEFAULT_PAST_PROJECT_SHARE_NAME = 'Past Project Curation';

export interface PastProjectShareSummary {
    id: string;
    name: string;
    note: string;
    version: number;
    share_url: string;
    row_count: number;
    created_at: string;
}

export interface PastProjectAISearchResponse {
    available: boolean;
    message?: string;
    query: string;
    results: ProjectTableRow[];
    usage?: {
        inputTokens?: number;
        outputTokens?: number;
        totalTokens?: number;
    };
}

export const toProjectGridRow = (project: ProjectTableRow): ProjectGridRow => ({
    id: project.id,
    semester_label: formatSemesterLabel(project.semester_label),
    class_code: project.class_code,
    team_number: project.team_number,
    team_name: project.team_name,
    project_title: project.project_title,
    organization: project.organization,
    industry: project.industry,
    abstract: project.abstract,
    student_names: project.student_names,
    is_presenting: project.is_presenting == null ? '' : project.is_presenting ? 'Yes' : 'No',
});

export const scheduleProjectToGridRow = (row: ScheduleProjectRow): ProjectGridRow => ({
    semester_label: formatSemesterLabel(row.year_semester),
    class_code: row.class_code,
    team_number: row.team_number,
    team_name: row.team_name,
    project_title: row.project_title,
    organization: row.organization,
    industry: row.industry,
    abstract: row.abstract,
    student_names: row.student_names,
    is_presenting: row.is_presenting ? 'Yes' : 'No',
});

export const fetchCurrentProjects = async (): Promise<SemesterWithProjects> => {
    const response = await api.get<SemesterWithProjects>('/event/projects/');
    return response.data;
};

export const fetchCurrentProjectsFull = async (): Promise<SemesterWithFullProjects> => {
    const response = await api.get<SemesterWithFullProjects>('/event/projects/');
    return response.data;
};

export const fetchPastProjectArchive = async (
    query: PastProjectArchiveQuery = {},
    signal?: AbortSignal,
): Promise<PaginatedResponse<CompactPastProjectRow>> => {
    const response = await api.get<PaginatedResponse<CompactPastProjectRow>>('/projects/archive/', {
        params: query,
        signal,
    });
    return response.data;
};

export const compactProjectToGridRow = (project: CompactPastProjectRow): ProjectGridRow => ({
    id: project.id,
    semester_label: formatSemesterLabel(project.semester_label),
    class_code: project.class_code,
    team_number: project.team_number,
    team_name: project.team_name,
    project_title: project.project_title,
    organization: project.organization,
    industry: project.industry,
    abstract: '',
    student_names: '',
    is_presenting: '',
});

export const fetchPastProjects = async (
    page = 1,
    pageSize = 5
): Promise<PaginatedResponse<SemesterWithProjects>> => {
    const response = await api.get<PaginatedResponse<SemesterWithProjects>>(
        `/projects/past/?page=${page}&page_size=${pageSize}`
    );
    return response.data;
};

export const searchPastProjectsWithAI = async (
    query: string,
    limit = 10,
): Promise<PastProjectAISearchResponse> => {
    const response = await authApi.post<PastProjectAISearchResponse>('/projects/past-ai-search/', {query, limit});
    return response.data;
};

export const fetchProjectDetail = async (id: string, signal?: AbortSignal): Promise<ProjectDetail> => {
    const response = await api.get<ProjectDetail>(`/projects/${id}/`, {signal});
    return response.data;
};

// Matches the inline detail loader's bound. Saving a large selection of archive rows
// would otherwise open one request per row at once.
const HYDRATION_CONCURRENCY = 4;
// A save must not fail because one of many detail requests hit a transient error, so each
// request is retried after these delays before its row is reported as failed.
const HYDRATION_RETRY_DELAYS_MS = [300, 900];
// Without a timeout one stalled request would leave a save "Saving…" indefinitely; a timeout is
// retried like any other network failure.
const HYDRATION_REQUEST_TIMEOUT_MS = 15_000;
// Once rows have kept failing for this long with no request answered in between, the API is down or
// stalled, and the rows not requested yet are reported as failed at once instead of each waiting out its own
// timeouts and retries. It counts from the first such failure, not from the last answer, so time the page
// spends suspended (a sleeping laptop) does not count. One slow or broken project does not trip it while
// the others keep loading.
const HYDRATION_STALL_MS = 30_000;

/** Archive rows arrive compact; their abstract and student names live only on the detail endpoint. */
export const needsProjectGridHydration = (row: ProjectGridRow) =>
    Boolean(row.id) && !row.abstract && !row.student_names;

const isRetryableDetailError = (error: unknown) => {
    const status = (error as {response?: {status?: number}}).response?.status;
    // No response at all is a network failure or timeout.
    return status === undefined || status === 408 || status === 429 || status >= 500;
};

const sleep = (ms: number, signal?: AbortSignal) =>
    new Promise<void>((resolve, reject) => {
        if (signal?.aborted) {
            reject(signal.reason);
            return;
        }
        const onAbort = () => {
            clearTimeout(timer);
            reject(signal?.reason);
        };
        const timer = setTimeout(() => {
            signal?.removeEventListener('abort', onAbort);
            resolve();
        }, ms);
        signal?.addEventListener('abort', onAbort, {once: true});
    });

const fetchProjectDetailWithRetry = async (id: string, signal?: AbortSignal): Promise<ProjectDetail> => {
    for (let attempt = 0; ; attempt += 1) {
        try {
            const response = await api.get<ProjectDetail>(`/projects/${id}/`, {
                signal,
                timeout: HYDRATION_REQUEST_TIMEOUT_MS,
            });
            return response.data;
        } catch (error) {
            if (signal?.aborted || attempt >= HYDRATION_RETRY_DELAYS_MS.length || !isRetryableDetailError(error)) {
                throw error;
            }
            await sleep(HYDRATION_RETRY_DELAYS_MS[attempt], signal);
        }
    }
};

export interface ProjectGridHydrationResult {
    rows: ProjectGridRow[];
    /** Input indexes whose details still failed after retries (worth trying again); returned unchanged. */
    failedIndexes: number[];
    /**
     * Input indexes the detail endpoint refused outright, e.g. a 404 for a project that was removed or whose
     * semester is unpublished. Retrying cannot help; returned unchanged.
     */
    unavailableIndexes: number[];
}

interface HydrationOptions {
    signal?: AbortSignal;
    /** Called after each detail request settles, over only the rows that needed one. */
    onProgress?: (done: number, total: number) => void;
}

/**
 * Fill in abstract/student names for compact rows. Unlike an all-or-nothing load, a row whose
 * details cannot be loaded is reported in `failedIndexes` or `unavailableIndexes` while every
 * other row is returned hydrated, so a save can keep what loaded. Rejects only when `signal` aborts.
 */
export const hydrateProjectGridRowsSettled = async (
    rows: ProjectGridRow[],
    {signal, onProgress}: HydrationOptions = {},
): Promise<ProjectGridHydrationResult> => {
    const hydrated = [...rows];
    const pendingIndexes = rows.flatMap((row, index) => (needsProjectGridHydration(row) ? [index] : []));
    const failedIndexes: number[] = [];
    const unavailableIndexes: number[] = [];
    let cursor = 0;
    let done = 0;
    // When the current run of failures began, or null while requests are being answered.
    let failingSince: number | null = null;
    const worker = async () => {
        while (cursor < pendingIndexes.length) {
            const index = pendingIndexes[cursor];
            cursor += 1;
            if (failingSince !== null && Date.now() - failingSince > HYDRATION_STALL_MS) {
                failedIndexes.push(index);
            } else {
                try {
                    hydrated[index] = toProjectGridRow(
                        await fetchProjectDetailWithRetry(rows[index].id as string, signal),
                    );
                    failingSince = null;
                } catch (error) {
                    if (signal?.aborted) throw error;
                    if (isRetryableDetailError(error)) {
                        failingSince ??= Date.now();
                        failedIndexes.push(index);
                    } else {
                        // Refused outright (e.g. a 404): the API is answering, this project is just not there.
                        failingSince = null;
                        unavailableIndexes.push(index);
                    }
                }
            }
            done += 1;
            onProgress?.(done, pendingIndexes.length);
        }
    };
    await Promise.all(
        Array.from({length: Math.min(HYDRATION_CONCURRENCY, pendingIndexes.length)}, worker),
    );
    const byIndex = (left: number, right: number) => left - right;
    return {
        rows: hydrated,
        failedIndexes: failedIndexes.sort(byIndex),
        unavailableIndexes: unavailableIndexes.sort(byIndex),
    };
};

export const createPastProjectShare = async (
    rows: ProjectGridRow[],
    name: string,
    note: string,
): Promise<PastProjectShare> => {
    // The client no longer sends a combined details_text field; the shared snapshot is the rows.
    const response = await authApi.post<PastProjectShare>('/projects/past-shares/', {
        rows,
        name,
        note,
    });
    return response.data;
};

export const fetchPastProjectShare = async (id: string): Promise<PastProjectShare> => {
    if (getAccessToken()) {
        try {
            const response = await authApi.get<PastProjectShare>(`/projects/past-shares/${id}/`, {
                requireFreshIdentity: true,
            });
            return response.data;
        } catch (err) {
            const status = (err as { response?: { status?: number } }).response?.status;
            if (status !== 401 || !isDefinitiveAuthFailure(err)) {
                throw err;
            }
        }
    }

    const response = await api.get<PastProjectShare>(`/projects/past-shares/${id}/`);
    return response.data;
};

export const updatePastProjectShare = async (
    id: string,
    payload: Partial<Pick<PastProjectShare, 'name' | 'rows' | 'note'>> &
        Pick<PastProjectShare, 'version'>,
): Promise<PastProjectShare> => {
    const response = await authApi.patch<PastProjectShare>(`/projects/past-shares/${id}/`, payload);
    return response.data;
};

export const listMyShares = async (): Promise<PastProjectShareSummary[]> => {
    const response = await authApi.get<PastProjectShareSummary[]>('/projects/past-shares/mine/');
    return response.data;
};

export const deleteShare = async (id: string): Promise<void> => {
    await authApi.delete(`/projects/past-shares/${id}/`);
};
