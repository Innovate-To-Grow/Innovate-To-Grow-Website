// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {NewsArticle, PaginatedResponse} from '../../../src/features/news/api';
import type {CMSEmbedResponse, CMSPageResponse} from '../../../src/features/cms/api';
import type {
  AssistantChatSuccessBody,
  AssistantChatUnavailableBody,
  AssistantConfig,
} from '../../../src/features/assistant/api';
import {newsList} from '../factories';
import {json} from './json';

export async function mockNews(
  page: Page,
  opts: {
    listByPage?: Record<number, PaginatedResponse<NewsArticle>>;
    list?: PaginatedResponse<NewsArticle>;
    detail?: NewsArticle;
    detailStatus?: number;
  } = {},
): Promise<void> {
  await page.route(/\/news\//, async (route) => {
    // The SPA route /news/:id also contains "/news/"; never intercept the
    // top-level document navigation, only the data fetches.
    if (route.request().resourceType() === 'document') {
      await route.fallback();
      return;
    }
    const url = new URL(route.request().url());
    const detailMatch = url.pathname.match(/\/news\/([^/]+)\/?$/);
    if (detailMatch && detailMatch[1]) {
      const status = opts.detailStatus ?? 200;
      if (status >= 400) {
        await route.fulfill(json({detail: 'Not found.'}, status));
        return;
      }
      await route.fulfill(json(opts.detail ?? {...newsList().results[0], content: '<p>Full article body.</p>'}));
      return;
    }
    const page_ = Number(url.searchParams.get('page') ?? '1');
    const payload = opts.listByPage?.[page_] ?? opts.list ?? newsList({page: page_});
    await route.fulfill(json(payload));
  });
}

export async function mockCmsPage(
  page: Page,
  slug: string,
  response: CMSPageResponse,
): Promise<void> {
  // The homepage uses its dedicated published-only endpoint; catch-all CMS
  // routes continue to use the route-specific pages endpoint.
  if (!slug) {
    await page.route('**/cms/homepage/', (route) =>
      route.fulfill(json(response)),
    );
    return;
  }
  await page.route(`**/cms/pages/${slug}/`, (route) => route.fulfill(json(response)));
}

// -- assistant ---------------------------------------------------------------

export async function mockAssistantConfig(
  page: Page,
  config?: AssistantConfig,
): Promise<void> {
  await page.route('**/assistant/config/', (route) =>
    route.fulfill(json(config ?? {enabled: true, welcome_message: 'Hi!', starter_questions: [], unavailable_message: 'Down.', max_message_chars: 2000})),
  );
}

export interface AssistantChatMockResult {
  messages: unknown[];
}

export async function mockAssistantChat(
  page: Page,
  opts: {
    successResponse?: AssistantChatSuccessBody;
    unavailableResponse?: AssistantChatUnavailableBody;
    /** Force 429 budget error. */
    budgetError?: boolean;
    /** Force 500 network error. */
    networkError?: boolean;
  } = {},
): Promise<AssistantChatMockResult> {
  const messages: unknown[] = [];

  await page.route('**/assistant/chat/', async (route) => {
    messages.push(route.request().postDataJSON());
    if (opts.networkError) {
      await route.abort('failed');
      return;
    }
    if (opts.budgetError) {
      await route.fulfill(json({detail: 'Budget exceeded.'}, 429));
      return;
    }
    if (opts.unavailableResponse) {
      await route.fulfill(json(opts.unavailableResponse));
      return;
    }
    await route.fulfill(
      json(
        opts.successResponse ?? {
          available: true,
          reply: 'Here is the answer to your question.',
          usage: {inputTokens: 10, outputTokens: 5, totalTokens: 15},
        },
      ),
    );
  });

  return {messages};
}

// -- CMS embed ---------------------------------------------------------------

export async function mockCmsEmbed(
  page: Page,
  embedSlug: string,
  response: CMSEmbedResponse,
): Promise<void> {
  await page.route(`**/cms/embed/${embedSlug}/`, (route) => route.fulfill(json(response)));
}

