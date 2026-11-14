import {PROJECT_REQUEST_TIMEOUT_MS} from './constants';
import {readCachedProjectDetail} from './projectDetailCache';
import {catalogFields, fetchProjectDetail, toProjectGridRow} from './catalog';
import type {ProjectGridRow, ProjectDetail, ProjectGridHydrationResult} from './types';

/**
 * How many project detail requests may be open at once, for a row's Details and for saving rows. The API is served
 * over HTTP/2, so they share one connection; the bound keeps a 100-row "View All Details" from opening 100 at once.
 */
export const PROJECT_DETAIL_CONCURRENCY = 6;

// A save must not fail because one of many detail requests hit a transient error, so each
// request is retried after these delays before its row is reported as failed.
const HYDRATION_RETRY_DELAYS_MS = [300, 900];
// Once rows have kept failing for this long with no request answered in between, the API is down or
// stalled, and the rows not requested yet are reported as failed at once instead of each waiting out its own
// timeouts and retries. It counts from the first such failure, not from the last answer, so time the page
// spends suspended (a sleeping laptop) does not count. One slow or broken project does not trip it while
// the others keep loading.
const HYDRATION_STALL_MS = 30_000;

/**
 * Archive rows arrive compact: their abstract lives only on the detail endpoint. Their student names may come
 * with them, so a row without an abstract is what needs its details.
 */
export const needsProjectGridHydration = (row: ProjectGridRow) => Boolean(row.id) && !row.abstract;

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
    // Rows whose Details were just opened are not requested again.
    const cached = readCachedProjectDetail(id);
    if (cached) return cached;
    for (let attempt = 0; ; attempt += 1) {
        try {
            // A timeout is retried like any other network failure; without one a stalled request would leave a save
            // "Saving…" indefinitely.
            return await fetchProjectDetail(id, signal, PROJECT_REQUEST_TIMEOUT_MS);
        } catch (error) {
            if (signal?.aborted || attempt >= HYDRATION_RETRY_DELAYS_MS.length || !isRetryableDetailError(error)) {
                throw error;
            }
            await sleep(HYDRATION_RETRY_DELAYS_MS[attempt], signal);
        }
    }
};

/**
 * A row as its details load it. A current-semester id answers with its archive project once the team's semester is
 * archived, so the catalog goes with the id the row now has: the detail's own, else the row's while the id is the
 * same (an older server sends none). `current_project_id` is kept while the id is the same; a current row that
 * became its archive row gets its former id there, as /projects/all/ lists such a row, so a list loaded before the
 * import still matches it.
 */
const hydratedGridRow = (row: ProjectGridRow, detail: ProjectDetail): ProjectGridRow => {
    const sameId = detail.id === row.id;
    const formerCurrentId = !sameId && row.catalog === 'current' ? row.id : undefined;
    return {
        ...toProjectGridRow(detail),
        ...catalogFields({
            catalog: detail.catalog ?? (sameId ? row.catalog : undefined),
            current_project_id: detail.current_project_id || (sameId ? row.current_project_id : formerCurrentId),
        }),
    };
};

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
    const hydrateIndex = async (index: number) => {
        try {
            const row = rows[index];
            hydrated[index] = hydratedGridRow(row, await fetchProjectDetailWithRetry(row.id as string, signal));
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
    };
    const worker = async () => {
        while (cursor < pendingIndexes.length) {
            const index = pendingIndexes[cursor];
            cursor += 1;
            if (failingSince !== null && Date.now() - failingSince > HYDRATION_STALL_MS) {
                failedIndexes.push(index);
            } else {
                await hydrateIndex(index);
            }
            done += 1;
            onProgress?.(done, pendingIndexes.length);
        }
    };
    await Promise.all(
        Array.from({length: Math.min(PROJECT_DETAIL_CONCURRENCY, pendingIndexes.length)}, worker),
    );
    const byIndex = (left: number, right: number) => left - right;
    return {
        rows: hydrated,
        failedIndexes: failedIndexes.sort(byIndex),
        unavailableIndexes: unavailableIndexes.sort(byIndex),
    };
};
