import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {NewsPage} from '@/routes/NewsPage/NewsPage';
import {fetchNews} from '@/features/news';
import type {NewsArticle, PaginatedResponse} from '@/features/news';

vi.mock('@/features/news', () => ({
  fetchNews: vi.fn(),
}));

const article = (overrides: Partial<NewsArticle> = {}): NewsArticle => ({
  id: '11111111-1111-4111-8111-111111111111',
  title: 'First Article',
  source_url: 'https://example.com/first',
  summary: 'A short summary.',
  image_url: 'https://example.com/first.png',
  author: 'Ada',
  published_at: '2026-06-15T12:00:00Z',
  ...overrides,
});

const pageOf = (
  results: NewsArticle[],
  overrides: Partial<PaginatedResponse<NewsArticle>> = {},
): PaginatedResponse<NewsArticle> => ({
  count: results.length,
  next: null,
  previous: null,
  results,
  ...overrides,
});

describe('NewsPage', () => {
  beforeEach(() => {
    vi.mocked(fetchNews).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the loading state while the first page is in flight', () => {
    vi.mocked(fetchNews).mockReturnValue(new Promise<never>(() => {}));

    render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows an error message when the fetch fails', async () => {
    vi.mocked(fetchNews).mockRejectedValue(new Error('boom'));

    render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Unable to load news.')).toBeInTheDocument();
  });

  it('shows the empty state when there are no articles', async () => {
    vi.mocked(fetchNews).mockResolvedValue(pageOf([]));

    render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('No news articles available.')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'News'})).toBeInTheDocument();
  });

  it('renders article cards with images, summaries, and dates', async () => {
    vi.mocked(fetchNews).mockResolvedValue(pageOf([article()]));

    const {container} = render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {name: 'First Article'})).toBeInTheDocument();
    expect(screen.getByRole('img', {name: 'First Article'})).toHaveAttribute(
      'src',
      'https://example.com/first.png',
    );
    expect(screen.getByText('A short summary.')).toBeInTheDocument();
    expect(container.querySelector('time')?.textContent).toMatch(/\d{4}/);
  });

  it('renders a placeholder image and omits the summary when missing', async () => {
    vi.mocked(fetchNews).mockResolvedValue(
      pageOf([article({image_url: '', summary: ''})]),
    );

    const {container} = render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {name: 'First Article'})).toBeInTheDocument();
    expect(screen.queryByRole('img', {name: 'First Article'})).toBeNull();
    expect(container.querySelector('.news-card-placeholder')).toBeInTheDocument();
    expect(container.querySelector('.news-card-summary')).toBeNull();
  });

  it('paginates forward through the news pages', async () => {
    vi.mocked(fetchNews).mockImplementation((page = 1) => {
      if (page === 1) {
        return Promise.resolve(
          pageOf([article()], {
            count: 25,
            next: 'https://example.com/news?page=2',
            previous: null,
          }),
        );
      }
      return Promise.resolve(
        pageOf(
          [
            article({
              id: '22222222-2222-4222-8222-222222222222',
              title: 'Second Article',
            }),
          ],
          {
            count: 25,
            next: null,
            previous: 'https://example.com/news?page=1',
          },
        ),
      );
    });

    render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', {name: 'First Article'})).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();

    const nextButton = screen.getByRole('button', {name: 'Next'});
    const previousButton = screen.getByRole('button', {name: 'Previous'});
    expect(nextButton).toBeEnabled();
    expect(previousButton).toBeDisabled();

    fireEvent.click(nextButton);

    expect(await screen.findByRole('heading', {name: 'Second Article'})).toBeInTheDocument();
    expect(fetchNews).toHaveBeenCalledWith(2);
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();

    expect(screen.getByRole('button', {name: 'Next'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Previous'})).toBeEnabled();

    fireEvent.click(screen.getByRole('button', {name: 'Previous'}));

    expect(await screen.findByRole('heading', {name: 'First Article'})).toBeInTheDocument();
    expect(fetchNews).toHaveBeenCalledWith(1);
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });
});
