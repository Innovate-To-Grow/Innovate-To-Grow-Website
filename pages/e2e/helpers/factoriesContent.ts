import type {EventSchedulePayload} from '../../src/features/events/api';
import type {NewsArticle, PaginatedResponse} from '../../src/features/news/api';
import type {CMSEmbedResponse, CMSPageResponse} from '../../src/features/cms/api';
import type {
  AssistantChatSuccessBody,
  AssistantChatUnavailableBody,
  AssistantConfig,
} from '../../src/features/assistant/api';

export function newsArticle(overrides: Partial<NewsArticle> = {}): NewsArticle {
  return {
    id: 'news-e2e-1',
    title: 'E2E News Headline',
    source_url: 'https://news.ucmerced.edu/e2e',
    summary: 'A concise summary of the E2E news article.',
    image_url: '',
    author: 'Newsroom',
    published_at: '2026-04-01T12:00:00Z',
    ...overrides,
  };
}

export function newsList(
  options: {count?: number; page?: number; pageSize?: number; results?: NewsArticle[]} = {},
): PaginatedResponse<NewsArticle> {
  const pageSize = options.pageSize ?? 12;
  const page = options.page ?? 1;
  const results =
    options.results ??
    Array.from({length: Math.min(pageSize, options.count ?? 3)}, (_, i) =>
      newsArticle({id: `news-e2e-${(page - 1) * pageSize + i + 1}`, title: `E2E News ${(page - 1) * pageSize + i + 1}`}),
    );
  const count = options.count ?? results.length;
  return {
    count,
    next: page * pageSize < count ? `/news/?page=${page + 1}&page_size=${pageSize}` : null,
    previous: page > 1 ? `/news/?page=${page - 1}&page_size=${pageSize}` : null,
    results,
  };
}

export function schedulePayload(overrides: Partial<EventSchedulePayload> = {}): EventSchedulePayload {
  return {
    event: {
      id: 'event-e2e',
      name: 'E2E Showcase',
      slug: 'e2e-showcase',
      date: '2026-05-01T18:00:00Z',
      location: 'E2E Hall',
      description: 'End-to-end showcase schedule.',
    },
    show_winners: false,
    grand_winners: [],
    expo: {title: 'Expo', location: 'Lobby', items: []},
    presentations_title: 'Presentations',
    sections: [],
    awards: {title: 'Awards', location: 'Main Stage', items: []},
    projects: [
      {
        id: 'project-e2e-1',
        track: 1,
        order: 3,
        year_semester: '2026 Spring',
        class_code: 'CSE 120',
        team_number: '7',
        team_name: 'Team Helix',
        project_title: 'Adaptive Irrigation Dashboard',
        organization: 'Acme Corp',
        industry: 'Agriculture',
        abstract: 'A dashboard that optimizes irrigation schedules.',
        student_names: 'Ada Lovelace, Alan Turing',
        is_presenting: true,
        tooltip: '',
      },
    ],
    ...overrides,
  };
}

export function cmsAcknowledgementPage(overrides: Partial<CMSPageResponse> = {}): CMSPageResponse {
  return {
    slug: 'acknowledgement',
    route: '/acknowledgement',
    title: 'Partners & Sponsors',
    page_css_class: '',
    meta_description: '',
    blocks: [
      {
        block_type: 'rich_text',
        sort_order: 0,
        data: {heading: 'Partners & Sponsors', heading_level: 1, body_html: '<p>Thank you to our sponsors.</p>'},
      },
      {
        block_type: 'sponsor_year',
        sort_order: 10,
        data: {
          year: '2025',
          sponsors: [{name: 'Acme Corp', logo_url: ''}],
        },
      },
    ],
    ...overrides,
  };
}

// -- assistant -----------------------------------------------------------

export function assistantConfig(overrides: Partial<AssistantConfig> = {}): AssistantConfig {
  return {
    enabled: true,
    welcome_message: 'Hi! I can help answer questions about Innovate to Grow.',
    starter_questions: [
      'What is Innovate to Grow?',
      'How do I get involved as a sponsor?',
      'When is the next event?',
    ],
    unavailable_message: 'The assistant is currently unavailable.',
    max_message_chars: 2000,
    ...overrides,
  };
}

export function assistantChatSuccess(
  overrides: Partial<AssistantChatSuccessBody> = {},
): AssistantChatSuccessBody {
  return {
    available: true,
    reply: 'Innovate to Grow is a program at UC Merced that connects students with industry sponsors.',
    usage: {inputTokens: 50, outputTokens: 20, totalTokens: 70},
    ...overrides,
  };
}

export function assistantChatUnavailable(
  overrides: Partial<AssistantChatUnavailableBody> = {},
): AssistantChatUnavailableBody {
  return {
    available: false,
    message: 'The assistant is currently unavailable.',
    ...overrides,
  };
}

// -- CMS embed -----------------------------------------------------------

export function cmsEmbedResponse(overrides: Partial<CMSEmbedResponse> = {}): CMSEmbedResponse {
  return {
    widget_type: 'blocks',
    blocks: [
      {
        block_type: 'rich_text',
        sort_order: 0,
        data: {body_html: '<p>Embedded content block.</p>'},
      },
    ],
    page_css_class: '',
    ...overrides,
  };
}

// -- generic CMS page ----------------------------------------------------

export function cmsPageResponse(overrides: Partial<CMSPageResponse> = {}): CMSPageResponse {
  return {
    slug: 'about',
    route: '/about',
    title: 'About Us',
    page_css_class: '',
    meta_description: '',
    blocks: [
      {
        block_type: 'rich_text',
        sort_order: 0,
        data: {body_html: '<h2>Who We Are</h2><p>Innovate to Grow connects UC Merced students with industry.</p>'},
      },
    ],
    ...overrides,
  };
}
