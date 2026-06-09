import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {NewsPage} from '@/routes/NewsPage/NewsPage';
import type {NewsArticle, PaginatedResponse} from '@/features/news';

const newsMocks = vi.hoisted(() => ({
  fetchNews: vi.fn(),
}));

vi.mock('@/features/news', async () => {
  const actual = await vi.importActual<typeof import('@/features/news')>('@/features/news');
  return {
    ...actual,
    fetchNews: newsMocks.fetchNews,
  };
});

const article = (id: string, title: string, image_url = ''): NewsArticle => ({
  id,
  title,
  source_url: 'https://example.com/news',
  summary: `${title} summary`,
  image_url,
  author: 'Author',
  published_at: '2026-05-01T12:00:00Z',
});

const page = (overrides: Partial<PaginatedResponse<NewsArticle>> = {}): PaginatedResponse<NewsArticle> => ({
  count: 13,
  next: '/news/?page=2',
  previous: null,
  results: [article('1', 'First story', 'https://example.com/image.jpg')],
  ...overrides,
});

const renderNews = () => render(<MemoryRouter><NewsPage /></MemoryRouter>);

describe('NewsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    newsMocks.fetchNews.mockResolvedValue(page());
  });

  it('renders articles and paginates through results', async () => {
    newsMocks.fetchNews
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(page({
        next: null,
        previous: '/news/?page=1',
        results: [article('2', 'Second story')],
      }));

    renderNews();

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(await screen.findByRole('link', {name: /First story/})).toHaveAttribute('href', '/news/1');
    expect(screen.getByText('May 1, 2026')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Next'}));
    await waitFor(() => expect(newsMocks.fetchNews).toHaveBeenCalledWith(2));
    expect(await screen.findByRole('link', {name: /Second story/})).toHaveAttribute('href', '/news/2');
    expect(screen.getByRole('button', {name: 'Next'})).toBeDisabled();
  });

  it('renders empty and error states', async () => {
    newsMocks.fetchNews.mockResolvedValueOnce(page({count: 0, next: null, previous: null, results: []}));
    const empty = renderNews();
    expect(await screen.findByText('No news articles available.')).toBeInTheDocument();
    empty.unmount();

    newsMocks.fetchNews.mockRejectedValueOnce(new Error('offline'));
    renderNews();
    expect(await screen.findByText('Unable to load news.')).toBeInTheDocument();
  });
});
