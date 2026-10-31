// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page, Route} from '@playwright/test';
import type {
  PastProjectAISearchResponse,
  PastProjectShare,
  ProjectDetail,
  ProjectTableRow,
} from '../../../src/features/projects/api';
import {json} from './json';

/** A compact list row, as `/projects/archive/` sends it: no abstract. */
const compactRow = (row: ProjectTableRow) => ({
  id: row.id, semester_label: row.semester_label, class_code: row.class_code,
  team_number: row.team_number, team_name: row.team_name, project_title: row.project_title,
  organization: row.organization, industry: row.industry, track: row.track,
  presentation_order: row.presentation_order,
});

/** One `?page=` of `rows` (`page_size` 20 by default), each as `toResult` sends it. */
function fulfillListPage(route: Route, rows: ProjectTableRow[], toResult: (row: ProjectTableRow) => object) {
  const url = new URL(route.request().url());
  const pageNumber = Number(url.searchParams.get('page') ?? 1);
  const pageSize = Number(url.searchParams.get('page_size') ?? 20);
  // ?search= matches the fields the API searches, abstracts included, case-insensitively.
  const search = url.searchParams.get('search')?.toLowerCase();
  const matching = search
    ? rows.filter((row) =>
        [
          row.project_title, row.team_name, row.team_number, row.organization, row.industry, row.class_code,
          row.abstract, row.student_names,
        ].some((value) => value.toLowerCase().includes(search)),
      )
    : rows;
  const start = (pageNumber - 1) * pageSize;
  const results = matching.slice(start, start + pageSize).map(toResult);
  return route.fulfill(json({count: matching.length, next: null, previous: null, results}));
}

/** `/projects/<id>/` for each of `rows`, as given; any other id goes on to the next handler. */
async function mockRowDetails(page: Page, rows: ProjectTableRow[]): Promise<void> {
  await page.route(/\/projects\/[^/]+\/(?:\?.*)?$/, async (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2);
    const row = rows.find((project) => project.id === id);
    if (!row) return route.fallback();
    await route.fulfill(json(row));
  });
}

export async function mockPastProjects(page: Page, rows: ProjectTableRow[]): Promise<void> {
  await mockRowDetails(page, rows);
  await page.route(/\/projects\/archive\/(?:\?.*)?$/, (route) => fulfillListPage(route, rows, compactRow));
}

/**
 * `/projects/all/`, the list All Projects and a curation owner's "Add More Projects" search: `rows` in the order
 * given (the API lists the active schedule's projects first), paged and searched like `/projects/archive/`, with
 * the fields it adds. A row without `catalog` is an archive row. Their details are served too.
 */
export async function mockAllProjects(page: Page, rows: ProjectTableRow[]): Promise<void> {
  await mockRowDetails(page, rows);
  await page.route(/\/projects\/all\/(?:\?.*)?$/, (route) =>
    fulfillListPage(route, rows, (row) => {
      const catalog = row.catalog ?? 'archive';
      return {
        ...compactRow(row),
        catalog,
        is_presenting: catalog === 'current' ? Boolean(row.is_presenting) : null,
        current_project_id: row.current_project_id ?? null,
      };
    }),
  );
}

export interface PastProjectShareMockController {
  patchPayloads: Partial<PastProjectShare>[];
  deleted: boolean;
  getCurrent: () => PastProjectShare;
  replaceCurrent: (share: PastProjectShare) => void;
}

export async function mockPastProjectShare(
  page: Page,
  share: PastProjectShare,
): Promise<PastProjectShareMockController> {
  let current = {...share};
  const patchPayloads: Partial<PastProjectShare>[] = [];
  let deleted = false;

  await page.route(/\/projects\/past-shares\/[^/]+\/?(\?.*)?$/, async (route) => {
    const method = route.request().method();
    if (deleted) {
      await route.fulfill(json({detail: 'Not found.'}, 404));
      return;
    }
    if (method === 'PATCH' || method === 'PUT') {
      const body = (route.request().postDataJSON() ?? {}) as Partial<PastProjectShare>;
      patchPayloads.push(body);
      if (body.version !== current.version) {
        await route.fulfill(
          json(
            {
              code: 'stale_snapshot',
              detail: 'This shared project changed.',
              current,
            },
            409,
          ),
        );
        return;
      }
      current = {...current, ...body, version: current.version + 1};
      await route.fulfill(json(current));
      return;
    }
    if (method === 'DELETE') {
      deleted = true;
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json(current));
  });

  return {
    patchPayloads,
    get deleted() {
      return deleted;
    },
    getCurrent: () => ({...current}),
    replaceCurrent: (nextShare) => {
      current = {...nextShare};
    },
  };
}

export async function mockProjectDetail(
  page: Page,
  detail: ProjectDetail,
  opts: {status?: number} = {},
): Promise<void> {
  await page.route(`**/projects/${detail.id}/`, (route) => {
    if (opts.status && opts.status >= 400) {
      route.fulfill(json({detail: 'Not found.'}, opts.status));
      return;
    }
    route.fulfill(json(detail));
  });
}

// -- AI search ---------------------------------------------------------------

export interface AiSearchMockResult {
  queries: unknown[];
}

export async function mockAiSearch(
  page: Page,
  opts: {
    response?: PastProjectAISearchResponse;
    /** Return 401 for unauthenticated tests. */
    status?: number;
  } = {},
): Promise<AiSearchMockResult> {
  const queries: unknown[] = [];

  await page.route('**/projects/past-ai-search/', async (route) => {
    queries.push(route.request().postDataJSON());
    const status = opts.status ?? 200;
    if (status >= 400) {
      await route.fulfill(json({detail: 'Unauthorized.'}, status));
      return;
    }
    await route.fulfill(
      json(
        opts.response ?? {
          available: true,
          query: '',
          results: [],
        },
      ),
    );
  });

  return {queries};
}

