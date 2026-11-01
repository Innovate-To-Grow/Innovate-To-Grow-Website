// Which project list a builder page searches: Past Projects (the published archive) or All Projects (the archive and
// the active schedule's teams). The parts both pages share read it from context. Without a provider they get Past
// Projects, so a page or test that sets none behaves as it did before All Projects existed.
import {createContext, useContext} from 'react';
import type {ProjectAISearchScope, ProjectGridRow} from '@/features/projects/api';
import type {RemoteRowSearch} from '../components/grid/state/useRemoteSearchMatches';
import {PAST_PROJECTS_CATALOG} from './catalogs';

export type ProjectCatalogKey = 'past' | 'all';

/** How the builder's states, messages and help name the list it searches. */
export interface ProjectCatalogCopy {
  /** The loading line while the rows load ("Loading past projects…"). */
  loading: string;
  /** When the first load failed, next to Try Again. */
  loadFailed: string;
  /** While a table's Refresh Search Table reloads the rows, once it has, and when it could not. */
  refreshing: string;
  refreshed: (tableCount: number) => string;
  refreshFailed: string;
  /** The AI search field's placeholder, the line while a search runs, and when it finds nothing. */
  aiPlaceholder: string;
  aiSearching: string;
  aiNoResults: string;
  /** The AI table's description, and the stack's message once every table is deleted. */
  aiDescription: string;
  noTablesMessage: string;
  /** The help's phrases: what "+ Search Table" searches, what an AI table loads, what Refresh Search Table reloads. */
  helpSearchSource: string;
  helpAIResults: string;
  helpRefreshSource: string;
  /** The partner-page widget, as the reports about a handed-over draft name it ("Past Projects widget"). */
  widgetName: string;
  /** Handed-over projects the list no longer has. */
  handoverMissing: (count: number) => string;
}

export interface ProjectCatalog {
  key: ProjectCatalogKey;
  /** The builder's route: where the widget hands a draft over, and where sign-in and saving continue. */
  path: string;
  /** The page's heading and name ("Continue in Past Projects"). */
  title: string;
  /** The paragraph under the heading. */
  lede: string;
  /** Every row the search tables search. Stable, so a hook can tell one list's rows from another's. */
  loadRows: (signal?: AbortSignal) => Promise<ProjectGridRow[]>;
  /** The server's search over what the rows leave out (abstracts), for a search table (useRemoteSearchMatches). */
  searchRemote: RemoteRowSearch;
  /** The `scope` an AI search table sends. */
  aiScope: ProjectAISearchScope;
  copy: ProjectCatalogCopy;
}

export const ProjectCatalogContext = createContext<ProjectCatalog>(PAST_PROJECTS_CATALOG);

export const useProjectCatalog = () => useContext(ProjectCatalogContext);
