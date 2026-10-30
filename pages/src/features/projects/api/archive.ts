// The past-projects archive list: compact rows, a page at a time or all at once, and the server's search over it.
// Its own module so unit tests can stub the search a Past Projects table sends while a visitor types
// (src/__tests__/core/setup.ts) without replacing the rest of the projects API.
import {api} from '@/lib/api';
import type {PaginatedResponse} from '@/types/api';
import {PROJECT_REQUEST_TIMEOUT_MS} from './constants';
import type {CompactPastProjectRow, PastProjectArchiveQuery} from './types';

/** The largest archive page the API serves (it rejects a bigger page_size). */
const ARCHIVE_PAGE_SIZE = 100;

export const fetchPastProjectArchive = async (
    query: PastProjectArchiveQuery = {},
    signal?: AbortSignal,
): Promise<PaginatedResponse<CompactPastProjectRow>> => {
    const response = await api.get<PaginatedResponse<CompactPastProjectRow>>('/projects/archive/', {
        params: query,
        signal,
        timeout: PROJECT_REQUEST_TIMEOUT_MS,
    });
    return response.data;
};

/**
 * Every archive row matching `query`. Page 1 tells how many there are, and the remaining pages are then requested
 * together: requested one after another, the 920-row archive took ten round trips to reach the screen.
 */
export const fetchAllPastProjectArchive = async (
    query: Omit<PastProjectArchiveQuery, 'page' | 'page_size'> = {},
    signal?: AbortSignal,
): Promise<CompactPastProjectRow[]> => {
    const firstPage = await fetchPastProjectArchive({...query, page: 1, page_size: ARCHIVE_PAGE_SIZE}, signal);
    const pageCount = Math.ceil(firstPage.count / ARCHIVE_PAGE_SIZE);
    const laterPages = await Promise.all(
        Array.from({length: Math.max(0, pageCount - 1)}, (_, index) =>
            fetchPastProjectArchive({...query, page: index + 2, page_size: ARCHIVE_PAGE_SIZE}, signal),
        ),
    );
    return [firstPage, ...laterPages].flatMap((page) => page.results);
};

/**
 * The ids of the archive projects the server finds for `query`. Its search also reads each project's abstract,
 * which the compact rows a list loads leave out, so a list adds these matches to the ones it finds itself.
 */
export const searchPastProjectArchiveIds = async (query: string, signal?: AbortSignal): Promise<ReadonlySet<string>> => {
    const projects = await fetchAllPastProjectArchive({search: query}, signal);
    return new Set(projects.map((project) => project.id));
};
