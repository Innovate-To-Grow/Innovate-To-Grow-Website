import type {ProjectGridRow} from '@/features/projects/api';

/** Which page a project title links to: the current-projects detail route or the past-projects one. */
export type ProjectGridLinkScope = 'current' | 'past';

export const getPastProjectDetailPath = (projectId: string) =>
  `/past-projects/project/${encodeURIComponent(projectId)}`;

export const getCurrentProjectDetailPath = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`;

/**
 * The page a past or all-projects list row's project is on: a current-semester project's own page (its id is an
 * event CurrentProject's, which `/projects/:id` reads), else the archive's; '' for a row without an id.
 */
export const getProjectRowDetailPath = ({id, catalog}: Pick<ProjectGridRow, 'id' | 'catalog'>) => {
  if (!id) return '';
  return catalog === 'current' ? getCurrentProjectDetailPath(id) : getPastProjectDetailPath(id);
};

/** History state of a project page opened from a list: the list's path and query, for its back link. */
export interface ProjectPageLinkState {
  from: string;
}

const currentFrontendOrigin = () => {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.location.origin;
};

/** getProjectRowDetailPath as a full URL, for a link that opens in a new tab or is copied into a note. */
export const getProjectRowDetailUrl = (row: Pick<ProjectGridRow, 'id' | 'catalog'>) => {
  const path = getProjectRowDetailPath(row);
  const origin = currentFrontendOrigin();
  return path && origin ? new URL(path, origin).href : path;
};

/**
 * The project page a row links to, or '' for rows without a project id (legacy snapshots). The 'past' scope (the
 * builders and shared curations) follows the row's own list; the current-projects pages link every row to theirs.
 */
export const getProjectGridRowHref = (row: Pick<ProjectGridRow, 'id' | 'catalog'>, scope: ProjectGridLinkScope) =>
  row.id ? (scope === 'past' ? getProjectRowDetailUrl(row) : getCurrentProjectDetailPath(row.id)) : '';

export const hasProjectGridDetails = (row: ProjectGridRow) => Boolean(row.id || row.abstract || row.student_names);
