// The project lists the builders search, as compact rows: the past-projects archive (/projects/archive/) and every
// project, the archive and the active schedule's (/projects/all/). A page at a time or all at once, and the server's
// search over them. Its own module so unit tests can stub the searches a search table sends while a visitor types
// (src/__tests__/core/setup.ts) without replacing the rest of the projects API.
import {api} from '@/lib/api';
import type {PaginatedResponse} from '@/types/api';
import {PROJECT_REQUEST_TIMEOUT_MS} from './constants';
import type {CompactPastProjectRow, PastProjectArchiveQuery} from './types';

/** The largest page either list serves (both reject a bigger page_size). */
const CATALOG_PAGE_SIZE = 100;

/** The paged project lists. /projects/all/ takes the archive's parameters and pages its rows the same way. */
export type ProjectCatalogEndpoint = '/projects/archive/' | '/projects/all/';

type WholeListQuery = Omit<PastProjectArchiveQuery, 'page' | 'page_size'>;

export const fetchCatalogPage = async (
    endpoint: ProjectCatalogEndpoint,
    query: PastProjectArchiveQuery = {},
    signal?: AbortSignal,
): Promise<PaginatedResponse<CompactPastProjectRow>> => {
    const response = await api.get<PaginatedResponse<CompactPastProjectRow>>(endpoint, {
        params: query,
        signal,
        timeout: PROJECT_REQUEST_TIMEOUT_MS,
    });
    return response.data;
};

export const fetchPastProjectArchive = (
    query: PastProjectArchiveQuery = {},
    signal?: AbortSignal,
): Promise<PaginatedResponse<CompactPastProjectRow>> => fetchCatalogPage('/projects/archive/', query, signal);

/** The pages after `firstPage`, requested together. */
const fetchLaterPages = async (
    endpoint: ProjectCatalogEndpoint,
    query: WholeListQuery,
    firstPage: PaginatedResponse<CompactPastProjectRow>,
    signal?: AbortSignal,
): Promise<CompactPastProjectRow[]> => {
    const pageCount = Math.ceil(firstPage.count / CATALOG_PAGE_SIZE);
    const laterPages = await Promise.all(
        Array.from({length: Math.max(0, pageCount - 1)}, (_, index) =>
            fetchCatalogPage(endpoint, {...query, page: index + 2, page_size: CATALOG_PAGE_SIZE}, signal),
        ),
    );
    return [firstPage, ...laterPages].flatMap((page) => page.results);
};

/**
 * Every row of `endpoint` matching `query`. Page 1 tells how many there are, and the remaining pages are then
 * requested together: requested one after another, the 920-row archive took ten round trips to reach the screen.
 */
const fetchWholeList = async (
    endpoint: ProjectCatalogEndpoint,
    query: WholeListQuery,
    signal?: AbortSignal,
): Promise<CompactPastProjectRow[]> => {
    const firstPage = await fetchCatalogPage(endpoint, {...query, page: 1, page_size: CATALOG_PAGE_SIZE}, signal);
    return fetchLaterPages(endpoint, query, firstPage, signal);
};

/** Every archive row matching `query`. */
export const fetchAllPastProjectArchive = (
    query: WholeListQuery = {},
    signal?: AbortSignal,
): Promise<CompactPastProjectRow[]> => fetchWholeList('/projects/archive/', query, signal);

/**
 * Each project once. The pages are requested together, so a schedule sync or an archive import between two of the
 * requests can move rows onto the next page: a row then arrives twice, or a current project arrives both as itself
 * and as the archive row that now stands in for it (and names it in `current_project_id`). The first copy is kept,
 * and the archive row rather than the current one.
 */
const eachProjectOnce = (rows: CompactPastProjectRow[]) => {
    const standsIn = new Set(rows.flatMap((row) => (row.current_project_id ? [row.current_project_id] : [])));
    const seen = new Set<string>();
    return rows.filter((row) => {
        if (seen.has(row.id) || standsIn.has(row.id)) return false;
        seen.add(row.id);
        return true;
    });
};

/**
 * Every project the All Projects page lists that matches `query`: the active schedule's projects that are not
 * archived yet, then the archive.
 */
export const fetchAllProjectsCatalog = async (
    query: WholeListQuery = {},
    signal?: AbortSignal,
): Promise<CompactPastProjectRow[]> => eachProjectOnce(await fetchWholeList('/projects/all/', query, signal));

/**
 * The most projects a search may match for a list to fetch them all. "the" or "and" is in nearly every abstract
 * (900 of 920 projects): fetching their matches downloaded the whole archive again, a page at a time, for each
 * search table and each pause in typing, to add rows that say nothing about the query.
 */
export const MAX_ARCHIVE_SEARCH_MATCHES = 500;

/**
 * The ids of the projects `endpoint`'s search finds for `query`, or null, after one page, when more than
 * MAX_ARCHIVE_SEARCH_MATCHES match. An archive row that stands in for a current project answers for that project's
 * id too, so a list loaded before the team was archived still finds it.
 */
const searchListIds = async (
    endpoint: ProjectCatalogEndpoint,
    query: string,
    signal?: AbortSignal,
): Promise<ReadonlySet<string> | null> => {
    const search = {search: query};
    const firstPage = await fetchCatalogPage(endpoint, {...search, page: 1, page_size: CATALOG_PAGE_SIZE}, signal);
    if (firstPage.count > MAX_ARCHIVE_SEARCH_MATCHES) return null;
    const projects = await fetchLaterPages(endpoint, search, firstPage, signal);
    return new Set(
        projects.flatMap((project) =>
            project.current_project_id ? [project.id, project.current_project_id] : [project.id],
        ),
    );
};

/**
 * The ids of the archive projects the server finds for `query`. Its search also reads each project's abstract,
 * which the compact rows a list loads leave out, so a list adds these matches to the ones it finds itself.
 * Resolves to null when more than MAX_ARCHIVE_SEARCH_MATCHES projects match: the list then keeps the matches its
 * own text finds, and its count says the abstracts were not searched.
 */
export const searchPastProjectArchiveIds = (query: string, signal?: AbortSignal) =>
    searchListIds('/projects/archive/', query, signal);

/** searchPastProjectArchiveIds over /projects/all/, whose search reads a current project's abstract and students too. */
export const searchAllProjectIds = (query: string, signal?: AbortSignal) =>
    searchListIds('/projects/all/', query, signal);
