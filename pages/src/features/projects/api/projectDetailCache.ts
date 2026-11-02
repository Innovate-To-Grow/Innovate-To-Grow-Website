// Project details a row's Details already loaded, kept for a while so saving the same rows does not request them
// again. The inline Details loader writes them; the save hydration reads them.
import type {ProjectDetail} from './types';

/** How long loaded details are reused before they are requested again. */
export const PROJECT_DETAIL_CACHE_TTL_MS = 5 * 60 * 1000;
// A few pages of "View All Details" at 100 rows per page; the oldest entries go first.
const MAX_CACHED_DETAILS = 300;

const cachedDetails = new Map<string, {detail: ProjectDetail; expiresAt: number}>();

export const rememberProjectDetail = (detail: ProjectDetail) => {
    cachedDetails.delete(detail.id);
    cachedDetails.set(detail.id, {detail, expiresAt: Date.now() + PROJECT_DETAIL_CACHE_TTL_MS});
    if (cachedDetails.size > MAX_CACHED_DETAILS) {
        cachedDetails.delete(cachedDetails.keys().next().value as string);
    }
};

/** The project's details if they were loaded recently, else null. */
export const readCachedProjectDetail = (id: string): ProjectDetail | null => {
    const cached = cachedDetails.get(id);
    if (!cached) return null;
    if (cached.expiresAt <= Date.now()) {
        cachedDetails.delete(id);
        return null;
    }
    return cached.detail;
};
