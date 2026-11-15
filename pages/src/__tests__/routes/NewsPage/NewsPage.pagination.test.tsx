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
    // The site pager's page line (pagination.css): shown on phones and on paper, where the buttons do not print.
    expect(screen.getByText('Page 1 of 3')).toHaveClass('itg-pagination-info', 'news-pagination-info');
    expect(screen.getByRole('navigation', {name: 'News pages'})).toHaveClass('itg-pagination');
    const current = screen
      .getByRole('navigation', {name: 'News pages'})
      .querySelector('[aria-current="page"]');
    expect(current?.textContent).toBe('Page 1');

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

    fireEvent.click(screen.getByRole('button', {name: 'Page 3'}));
    expect(await screen.findByRole('heading', {name: 'Second Article'})).toBeInTheDocument();
    expect(fetchNews).toHaveBeenCalledWith(3);
    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
  });

  it('collapses distant pages into an ellipsis around the current page', async () => {
    vi.mocked(fetchNews).mockResolvedValue(
      pageOf([article()], {count: 120, next: 'https://example.com/news?page=2', previous: null}),
    );

    const {container} = render(
      <MemoryRouter>
        <NewsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Page 1 of 10')).toBeInTheDocument();
    const labels = Array.from(container.querySelectorAll('.news-pagination-pages li')).map(
      (item) => item.textContent,
    );
    expect(labels).toEqual(['Page 1', '2', '…', '10']);
    expect(screen.getByRole('button', {name: 'Page 10'})).toBeInTheDocument();
  });
});
