import {searchPastProjectsWithAI, toProjectGridRow, type ProjectAISearchScope} from '@/features/projects/api';
import {collectFieldMessages} from '@/lib/api/errorMessages';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import type {SearchTableState} from './types';

const AI_SEARCH_LIMIT = 10;

const createAISearchTableTitle = (query: string) => {
  const normalized = query.trim().replace(/\s+/g, ' ');
  const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}…` : normalized;
  return `AI Search Table: ${clipped}`;
};

// The API's reason when it gives one: `detail` (budget, provider errors), `message`, or a validation error on a
// field (`{"query": ["Query must be at most 2000 characters."]}`), which a retry would only repeat.
const getAISearchErrorMessage = (error: unknown) => {
  const data = (error as {response?: {data?: unknown}} | null)?.response?.data;
  const [reason] =
    data && typeof data === 'object'
      ? collectFieldMessages(data as Record<string, unknown>, (message) => Boolean(message.trim()), ['code'])
      : [];
  return reason || 'AI search is unavailable right now. Please try again.';
};

// `available: false` means AI search is not set up on this site. The API's own message is meant for the site's
// administrators, so members get this instead.
const AI_SEARCH_NOT_AVAILABLE_MESSAGE =
  'AI search is not available on this site right now. You can still find projects with a regular search table.';

type AISearchResponse = Awaited<ReturnType<typeof searchPastProjectsWithAI>>;

interface AIResultsOptions {
  filterAIRows: (rows: ProjectGridRow[]) => ProjectGridRow[];
  /** When every AI result was filtered out, and when AI search found none. */
  allAIRowsFilteredMessage: string;
  noResultsMessage: string;
}

/** The rows and title an AI search loads into its table, or why it loads none. */
const aiSearchOutcome = (
  response: AISearchResponse,
  query: string,
  {filterAIRows, allAIRowsFilteredMessage, noResultsMessage}: AIResultsOptions,
): {error: string} | {rows: ProjectGridRow[]; title: string} => {
  if (!response.available) {
    return {error: AI_SEARCH_NOT_AVAILABLE_MESSAGE};
  }
  const aiRows = filterAIRows(response.results.map(toProjectGridRow));
  if (!aiRows.length) {
    return {error: response.results.length ? allAIRowsFilteredMessage : noResultsMessage};
  }
  return {rows: aiRows, title: createAISearchTableTitle(response.query || query)};
};

export type UpdateSearchTable = (tableId: string, update: (table: SearchTableState) => SearchTableState) => void;

interface AISearchRunnerOptions extends AIResultsOptions {
  isAuthenticated: boolean;
  updateSearchTable: UpdateSearchTable;
  /** What the search ranks (the catalog's), and what its table says while it runs. */
  scope: ProjectAISearchScope;
  searchingMessage: string;
  onMessage: (message: string) => void;
}

/** Runs an AI table's query and loads its results into that table, or says in it why there are none. */
export const createAISearchRunner =
  ({isAuthenticated, updateSearchTable, scope, searchingMessage, onMessage, ...results}: AISearchRunnerOptions) =>
  async (tableId: string, query: string) => {
    if (!isAuthenticated) {
      return;
    }
    const finish = (message: string, messageTone: SearchTableState['messageTone'], extra = {}) =>
      updateSearchTable(tableId, (table) => ({...table, isLoading: false, message, messageTone, ...extra}));

    updateSearchTable(tableId, (table) => ({
      ...table,
      isLoading: true,
      message: searchingMessage,
      messageTone: 'loading',
    }));
    try {
      const outcome = aiSearchOutcome(await searchPastProjectsWithAI(query, AI_SEARCH_LIMIT, scope), query, results);
      if ('error' in outcome) {
        finish(outcome.error, 'error');
        return;
      }
      updateSearchTable(tableId, (table) => ({
        ...table,
        initialRows: outcome.rows,
        isLoading: false,
        message: `${outcome.rows.length} AI result${outcome.rows.length === 1 ? '' : 's'} loaded into this table.`,
        messageTone: 'success',
        rowsResetKey: (table.rowsResetKey ?? 0) + 1,
        title: outcome.title,
      }));
      onMessage('');
    } catch (err) {
      finish(getAISearchErrorMessage(err), 'error');
    }
  };
