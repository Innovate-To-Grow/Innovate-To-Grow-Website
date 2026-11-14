export type {
    ProjectSummary,
    ProjectTableRow,
    CompactPastProjectRow,
    PastProjectArchiveQuery,
    ProjectGridRow,
    ProjectDetail,
    SemesterWithProjects,
    SemesterWithFullProjects,
    PastProjectShare,
    PastProjectShareSummary,
    PastProjectAISearchResponse,
    ProjectGridHydrationResult,
    ProjectCatalogSource,
    ProjectAISearchScope,
} from './types';

export type {PaginatedResponse} from '@/types/api';

export {DEFAULT_PAST_PROJECT_SHARE_NAME, DEFAULT_PROJECT_SHARE_NAME, PROJECT_REQUEST_TIMEOUT_MS} from './constants';
export {
    fetchAllPastProjectArchive,
    fetchAllProjectsCatalog,
    fetchCatalogPage,
    fetchPastProjectArchive,
    searchAllProjectIds,
    searchPastProjectArchiveIds,
    type ProjectCatalogEndpoint,
} from './archive';
export {PROJECT_DETAIL_CACHE_TTL_MS, readCachedProjectDetail, rememberProjectDetail} from './projectDetailCache';
export {
    compactProjectToGridRow,
    fetchCurrentProjects,
    fetchCurrentProjectsFull,
    fetchPastProjects,
    fetchProjectDetail,
    scheduleProjectToGridRow,
    searchPastProjectsWithAI,
    toProjectGridRow,
} from './catalog';
export {PROJECT_DETAIL_CONCURRENCY, hydrateProjectGridRowsSettled, needsProjectGridHydration} from './hydration';
export {createPastProjectShare, deleteShare, fetchPastProjectShare, listMyShares, updatePastProjectShare} from './shares';
