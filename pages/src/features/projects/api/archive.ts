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

/** The pages after `firstPage`, requested together. */
const fetchLaterArchivePages = async (
    query: Omit<PastProjectArchiveQuery, 'page' | 'page_size'>,
    firstPage: PaginatedResponse<CompactPastProjectRow>,
    signal?: AbortSignal,
): Promise<CompactPastProjectRow[]> => {
    const pageCount = Math.ceil(firstPage.count / ARCHIVE_PAGE_SIZE);
    const laterPages = await Promise.all(
        Array.from({length: Math.max(0, pageCount - 1)}, (_, index) =>
            fetchPastProjectArchive({...query, page: index + 2, page_size: ARCHIVE_PAGE_SIZE}, signal),
        ),
    );
    return [firstPage, ...laterPages].flatMap((page) => page.results);
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
    return fetchLaterArchivePages(query, firstPage, signal);
};

/**
 * The most projects a search may match for a list to fetch them all. "the" or "and" is in nearly every abstract
 * (900 of 920 projects): fetching their matches downloaded the whole archive again, a page at a time, for each
 * search table and each pause in typing, to add rows that say nothing about the query.
 */
export const MAX_ARCHIVE_SEARCH_MATCHES = 500;

/**
 * The ids of the archive projects the server finds for `query`. Its search also reads each project's abstract,
 * which the compact rows a list loads leave out, so a list adds these matches to the ones it finds itself.
 * Resolves to null, after one page, when more than MAX_ARCHIVE_SEARCH_MATCHES projects match: the list then keeps
 * the matches its own text finds.
 */
export const searchPastProjectArchiveIds = async (
    query: string,
    signal?: AbortSignal,
): Promise<ReadonlySet<string> | null> => {
    const search = {search: query};
    const firstPage = await fetchPastProjectArchive({...search, page: 1, page_size: ARCHIVE_PAGE_SIZE}, signal);
    if (firstPage.count > MAX_ARCHIVE_SEARCH_MATCHES) return null;
    const projects = await fetchLaterArchivePages(search, firstPage, signal);
    return new Set(projects.map((project) => project.id));
};
