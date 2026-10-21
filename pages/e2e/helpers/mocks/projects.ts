// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {
  PastProjectAISearchResponse,
  PastProjectShare,
  ProjectDetail,
  ProjectTableRow,
} from '../../../src/features/projects/api';
import {json} from './json';

export async function mockPastProjects(page: Page, rows: ProjectTableRow[]): Promise<void> {
  await page.route(/\/projects\/[^/]+\/(?:\?.*)?$/, async (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2);
    const row = rows.find((project) => project.id === id);
    if (!row) return route.fallback();
    await route.fulfill(json(row));
  });
  await page.route(/\/projects\/archive\/(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    const pageNumber = Number(url.searchParams.get('page') ?? 1);
    const pageSize = Number(url.searchParams.get('page_size') ?? 20);
    const start = (pageNumber - 1) * pageSize;
    const results = rows.slice(start, start + pageSize).map((row) => ({
      id: row.id, semester_label: row.semester_label, class_code: row.class_code,
      team_number: row.team_number, team_name: row.team_name, project_title: row.project_title,
      organization: row.organization, industry: row.industry, track: row.track,
      presentation_order: row.presentation_order,
    }));
    return route.fulfill(json({count: rows.length, next: null, previous: null, results}));
  });
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

