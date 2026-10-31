import {DEFAULT_PAST_PROJECT_SHARE_NAME, DEFAULT_PROJECT_SHARE_NAME} from '@/features/projects/api/constants';
import {ALL_PROJECTS_CATALOG, PAST_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';

/** How a curation names the list its projects come from: on its shared page and in its exports. */
export interface CurationBranding {
  /** The shared page's eyebrow, over the curation's name. */
  eyebrow: string;
  /** The line under an export's title. Left out, the exporters' own: "Innovate to Grow Past Projects". */
  exportHeading?: string;
  /** What an export's file name starts with ("past-projects-spring-picks.pdf"). */
  filePrefix: string;
  /**
   * The name of a curation saved without one or any note text of its owner's, as the server gives it
   * (share_names.default_share_name), and what one stored with a blank name is shown as.
   */
  defaultName: string;
  /** Where the shared page sends a visitor who wants to make a list of their own, and the link's words. */
  searchLink: {to: string; label: string};
}

const PAST_PROJECTS_BRANDING: CurationBranding = {
  eyebrow: 'Curation · Past Projects',
  filePrefix: 'past-projects',
  defaultName: DEFAULT_PAST_PROJECT_SHARE_NAME,
  searchLink: {to: PAST_PROJECTS_CATALOG.path, label: 'Search all past projects'},
};

const ALL_PROJECTS_BRANDING: CurationBranding = {
  eyebrow: 'Curation · All Projects',
  exportHeading: 'Innovate to Grow Projects',
  filePrefix: 'projects',
  defaultName: DEFAULT_PROJECT_SHARE_NAME,
  searchLink: {to: ALL_PROJECTS_CATALOG.path, label: 'Search all projects'},
};

/**
 * A curation holding a current-semester project is not a list of past projects, so it is named as All Projects names
 * its list. One of archive projects only reads as it always has, whichever page built it.
 */
export const curationBranding = (rows: readonly Pick<ProjectGridRow, 'catalog'>[]): CurationBranding =>
  rows.some((row) => row.catalog === 'current') ? ALL_PROJECTS_BRANDING : PAST_PROJECTS_BRANDING;
