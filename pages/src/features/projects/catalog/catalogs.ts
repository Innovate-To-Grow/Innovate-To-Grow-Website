// The project lists a builder page can search (projectCatalog.ts). Past Projects keeps the words its page has always
// used; All Projects names the whole list, not the archive.
import {
  compactProjectToGridRow,
  fetchAllPastProjectArchive,
  fetchAllProjectsCatalog,
  searchAllProjectIds,
  searchPastProjectArchiveIds,
} from '@/features/projects/api';
import {pluralize} from '../components/shared/utils/saveResults';
import type {ProjectCatalog} from './projectCatalog';

const isAre = (count: number) => (count === 1 ? 'is' : 'are');
const tables = (count: number) => (count === 1 ? 'table' : 'tables');

// Module-level, so each catalog's functions stay the same from render to render, and arrows that look the api
// functions up only when called, so a test that mocks part of the api module can still import this one.
const loadPastRows = async (signal?: AbortSignal) =>
  (await fetchAllPastProjectArchive({}, signal)).map(compactProjectToGridRow);
const searchPastRows: ProjectCatalog['searchRemote'] = (query, signal) => searchPastProjectArchiveIds(query, signal);

export const PAST_PROJECTS_CATALOG: ProjectCatalog = {
  key: 'past',
  path: '/past-projects',
  title: 'Past Projects',
  lede:
    'Search past Innovate to Grow projects, check the ones you want, and collect them into a curation. Save it to ' +
    'keep it and share it with a link, or export it.',
  loadRows: loadPastRows,
  searchRemote: searchPastRows,
  aiScope: 'past',
  copy: {
    loading: 'Loading past projects…',
    loadFailed: 'The past-project archive could not be loaded. Check your connection and try again.',
    refreshing: 'Refreshing this search table from the latest past-project archive…',
    refreshed: (count) => `Search ${tables(count)} refreshed from the latest past-project archive.`,
    refreshFailed:
      'This table was not refreshed: the past-project archive could not be loaded. Its rows are unchanged; ' +
      'click Refresh Search Table to try again.',
    aiPlaceholder: 'Ask about past projects…',
    aiSearching: 'Searching past projects with AI…',
    aiNoResults: 'AI search did not find matching past projects.',
    aiDescription:
      'Use AI to load matching past projects into this table, then check the projects you want and click Add to ' +
      'Curation.',
    noTablesMessage: 'No search tables are open. Add a new table to start searching past projects.',
    helpSearchSource: 'the same past-project archive',
    helpAIResults: 'matching past projects',
    helpRefreshSource: 'the archive',
    widgetName: 'Past Projects widget',
    handoverMissing: (count) =>
      `${pluralize(count, 'project')} from the Past Projects widget ${isAre(count)} no longer in the archive.`,
  },
};

// /projects/all/: the active schedule's projects that are not archived yet, then the archive. Its rows say which list
// they come from (`catalog`), so a current project links to its own page.
const loadAllRows = async (signal?: AbortSignal) =>
  (await fetchAllProjectsCatalog({}, signal)).map(compactProjectToGridRow);
const searchAllRows: ProjectCatalog['searchRemote'] = (query, signal) => searchAllProjectIds(query, signal);

export const ALL_PROJECTS_CATALOG: ProjectCatalog = {
  key: 'all',
  path: '/all-projects',
  title: 'All Projects',
  lede:
    "Search every Innovate to Grow project, this semester's teams and the archive, check the ones you want, and " +
    'collect them into a curation. Save it to keep it and share it with a link, or export it.',
  loadRows: loadAllRows,
  searchRemote: searchAllRows,
  aiScope: 'all',
  copy: {
    loading: 'Loading projects…',
    loadFailed: 'The project list could not be loaded. Check your connection and try again.',
    refreshing: 'Refreshing this search table from the latest project list…',
    refreshed: (count) => `Search ${tables(count)} refreshed from the latest project list.`,
    refreshFailed:
      'This table was not refreshed: the project list could not be loaded. Its rows are unchanged; ' +
      'click Refresh Search Table to try again.',
    aiPlaceholder: 'Ask about projects…',
    aiSearching: 'Searching projects with AI…',
    aiNoResults: 'AI search did not find matching projects.',
    aiDescription:
      'Use AI to load matching projects into this table, then check the projects you want and click Add to Curation.',
    noTablesMessage: 'No search tables are open. Add a new table to start searching projects.',
    helpSearchSource: 'the same project list',
    helpAIResults: 'matching projects',
    helpRefreshSource: 'the project list',
    widgetName: 'All Projects widget',
    handoverMissing: (count) =>
      `${pluralize(count, 'project')} from the All Projects widget ${isAre(count)} no longer listed.`,
  },
};
