import {useEffect, useState} from 'react';
import {useLocation, useNavigationType, useSearchParams} from 'react-router';
import {
  PROJECT_GRID_COLUMNS,
  type ProjectGridColumnKey,
  type ProjectGridSortDirection,
} from '../components/grid/contracts/projectGrid';
import {PROJECT_GRID_PAGE_SIZE_OPTIONS} from '../components/grid/state/useProjectGridTable';

/** What a current-projects list keeps in its URL, so Back from a project, a reload or a shared link shows it again. */
export interface ProjectListUrlState {
  search: string;
  classCode: string;
  industry: string;
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  /** 0-based; the URL counts from 1. */
  page: number;
  pageSize: number;
}

export const PROJECT_LIST_URL_DEFAULTS: ProjectListUrlState = {
  search: '',
  classCode: '',
  industry: '',
  sortField: 'class_code',
  sortDirection: 'asc',
  page: 0,
  pageSize: 10,
};

/** The query parameters, by state field. `value` is also how other pages link to a search (?value=farm). */
const PARAM_NAMES = {
  search: 'value',
  classCode: 'class',
  industry: 'industry',
  sortField: 'sort',
  sortDirection: 'dir',
  page: 'page',
  pageSize: 'per',
} as const satisfies Record<keyof ProjectListUrlState, string>;

const LIST_PARAMS = Object.values(PARAM_NAMES);
const SORT_FIELDS = new Set<string>(PROJECT_GRID_COLUMNS.map((column) => column.key));
const PAGE_SIZES: readonly number[] = PROJECT_GRID_PAGE_SIZE_OPTIONS;

/** Typing settles before the search reaches the URL: browsers limit how often a page may rewrite its history. */
export const SEARCH_URL_DELAY_MS = 400;

/** The list state a URL describes; anything missing or not understood is the default. */
export const readProjectListUrlState = (params: URLSearchParams): ProjectListUrlState => {
  const sort = params.get(PARAM_NAMES.sortField) ?? '';
  const page = Number(params.get(PARAM_NAMES.page));
  const pageSize = Number(params.get(PARAM_NAMES.pageSize));
  return {
    search: params.get(PARAM_NAMES.search) ?? '',
    classCode: params.get(PARAM_NAMES.classCode) ?? '',
    industry: params.get(PARAM_NAMES.industry) ?? '',
    sortField: SORT_FIELDS.has(sort) ? (sort as ProjectGridColumnKey) : PROJECT_LIST_URL_DEFAULTS.sortField,
    sortDirection: params.get(PARAM_NAMES.sortDirection) === 'desc' ? 'desc' : 'asc',
    page: Number.isInteger(page) && page >= 1 ? page - 1 : 0,
    pageSize: PAGE_SIZES.includes(pageSize) ? pageSize : PROJECT_LIST_URL_DEFAULTS.pageSize,
  };
};

/** `current` with the list's parameters set to `state` (defaults left out); other parameters are kept. */
export const writeProjectListUrlState = (current: URLSearchParams, state: ProjectListUrlState) => {
  const next = new URLSearchParams(current);
  LIST_PARAMS.forEach((name) => next.delete(name));
  const values: Record<keyof ProjectListUrlState, string> = {
    search: state.search.trim(),
    classCode: state.classCode,
    industry: state.industry,
    sortField: state.sortField === PROJECT_LIST_URL_DEFAULTS.sortField ? '' : state.sortField,
    sortDirection: state.sortDirection === 'desc' ? 'desc' : '',
    page: state.page > 0 ? String(state.page + 1) : '',
    pageSize: state.pageSize === PROJECT_LIST_URL_DEFAULTS.pageSize ? '' : String(state.pageSize),
  };
  (Object.keys(PARAM_NAMES) as Array<keyof ProjectListUrlState>).forEach((field) => {
    if (values[field]) next.set(PARAM_NAMES[field], values[field]);
  });
  return next;
};

const sameListParams = (left: URLSearchParams, right: URLSearchParams) =>
  LIST_PARAMS.every((name) => left.get(name) === right.get(name));

/** Marks the history entries the list rewrites itself, to tell them from a navigation to the list. */
const URL_SYNC_STATE = {projectListUrlSync: true};
const isUrlSync = (state: unknown) => (state as Partial<typeof URL_SYNC_STATE> | null)?.projectListUrlSync === true;

/**
 * A key for the list's state. It stays the same while the list writes its own state into the URL, and changes
 * when the visitor navigates to the list again (a link to it, or Back and Forward between two of its URLs), so a
 * list keyed by it starts over from the URL it then shows.
 */
export function useProjectListStateKey() {
  const location = useLocation();
  const navigationType = useNavigationType();
  const [keys, setKeys] = useState({location: location.key, state: location.key});
  let stateKey = keys.state;
  if (keys.location !== location.key) {
    stateKey = navigationType === 'REPLACE' && isUrlSync(location.state) ? keys.state : location.key;
    setKeys({location: location.key, state: stateKey});
  }
  return stateKey;
}

/** The list state the URL held when the list mounted. */
export function useInitialProjectListUrlState() {
  const [searchParams] = useSearchParams();
  const [initial] = useState(() => readProjectListUrlState(searchParams));
  return initial;
}

/**
 * Writes the list's state into the URL as it changes. The history entry is replaced (Back leaves the list rather
 * than stepping through its filters) and the page does not scroll. Nothing is written until `ready`: while the
 * rows load, the filters they offer do not exist yet and would read as cleared.
 */
export function useProjectListUrlSync(state: ProjectListUrlState, ready: boolean) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [settledSearch, setSettledSearch] = useState(state.search);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledSearch(state.search), SEARCH_URL_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [state.search]);

  const wanted = ready ? writeProjectListUrlState(new URLSearchParams(), {...state, search: settledSearch}).toString() : null;
  useEffect(() => {
    if (wanted === null) return;
    const next = new URLSearchParams(searchParams);
    LIST_PARAMS.forEach((name) => next.delete(name));
    new URLSearchParams(wanted).forEach((value, name) => next.append(name, value));
    if (sameListParams(next, searchParams)) return;
    setSearchParams(next, {replace: true, preventScrollReset: true, state: URL_SYNC_STATE});
  }, [searchParams, setSearchParams, wanted]);
}
