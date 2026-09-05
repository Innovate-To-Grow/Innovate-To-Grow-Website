import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {NewsDetailPage} from '@/routes/NewsDetailPage/NewsDetailPage';
import {fetchNewsDetail} from '@/features/news';
import type {NewsArticle} from '@/features/news';

vi.mock('@/features/news', () => ({
  fetchNewsDetail: vi.fn(),
}));

vi.mock('@/components/SafeHtml/SafeHtml', () => ({
  SafeHtml: ({html, className}: {html: string; className?: string}) => (
    <div className={className} data-testid="safe-html">{html}</div>
  ),
}));

const article = (overrides: Partial<NewsArticle> = {}): NewsArticle => ({
  id: '11111111-1111-4111-8111-111111111111',
  title: 'Detail Article',
  source_url: 'https://example.com/detail',
  summary: 'A summary.',
  image_url: 'https://example.com/card.png',
  author: 'Ada Lovelace',
  published_at: '2026-06-15T12:00:00Z',
  content: '<p>Full body.</p>',
  hero_image_url: 'https://example.com/hero.png',
  hero_caption: 'Hero caption',
  ...overrides,
});

const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/news/:id" element={<NewsDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('NewsDetailPage', () => {
  beforeEach(() => {
    vi.mocked(fetchNewsDetail).mockReset();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows the loading state while the article is in flight', () => {
    vi.mocked(fetchNewsDetail).mockReturnValue(new Promise<never>(() => {}));

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('scrolls to the top when the article loads', async () => {
    vi.mocked(fetchNewsDetail).mockResolvedValue(article());

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    await screen.findByRole('heading', {name: 'Detail Article'});
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
  });

  it('shows an error message with the back link when the fetch fails', async () => {
    vi.mocked(fetchNewsDetail).mockRejectedValue(new Error('boom'));

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    expect(await screen.findByText('Unable to load this article.')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /back to news/i}).getAttribute('href')).toBe('/news');
  });

  it('shows the not-found state when no id is present', () => {
    render(
      <MemoryRouter>
        <NewsDetailPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Article not found.')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /back to news/i}).getAttribute('href')).toBe('/news');
  });

  it('renders the full article with hero, author, safe content, and source link', async () => {
    vi.mocked(fetchNewsDetail).mockResolvedValue(article());

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    expect(await screen.findByRole('heading', {name: 'Detail Article'})).toBeInTheDocument();
    expect(screen.getByAltText('Detail Article')).toHaveAttribute(
      'src',
      'https://example.com/hero.png',
    );
    expect(screen.getByText('Hero caption')).toBeInTheDocument();
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByTestId('safe-html')).toHaveTextContent('Full body.');
    expect(screen.queryByText('A summary.')).toBeNull();
    expect(
      screen.getByRole('link', {name: 'View original article'}).getAttribute('href'),
    ).toBe('https://example.com/detail');
  });

  it('falls back to the summary and hides missing hero and author fields', async () => {
    vi.mocked(fetchNewsDetail).mockResolvedValue(
      article({
        content: undefined,
        hero_image_url: undefined,
        hero_caption: undefined,
        author: '',
      }),
    );

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    expect(await screen.findByRole('heading', {name: 'Detail Article'})).toBeInTheDocument();
    expect(screen.queryByAltText('Detail Article')).toBeNull();
    expect(screen.queryByText('Ada Lovelace')).toBeNull();
    expect(screen.queryByTestId('safe-html')).toBeNull();
    expect(screen.getByText('A summary.')).toBeInTheDocument();
  });

  it('aborts the in-flight request on unmount and ignores the resolved result', async () => {
    let resolveFetch!: (value: NewsArticle) => void;
    vi.mocked(fetchNewsDetail).mockReturnValue(
      new Promise<NewsArticle>((resolve) => {
        resolveFetch = resolve;
      }),
    );

    const {unmount} = renderPage('/news/11111111-1111-4111-8111-111111111111');

    await waitFor(() => expect(fetchNewsDetail).toHaveBeenCalled());
    const signal = vi.mocked(fetchNewsDetail).mock.calls[0][1];
    unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      resolveFetch(article());
      await Promise.resolve();
    });
  });

  it('ignores a rejected request that settles after unmount', async () => {
    let rejectFetch!: (reason?: unknown) => void;
    vi.mocked(fetchNewsDetail).mockReturnValue(
      new Promise<NewsArticle>((_resolve, reject) => {
        rejectFetch = reject;
      }),
    );

    const {unmount} = renderPage('/news/11111111-1111-4111-8111-111111111111');

    await waitFor(() => expect(fetchNewsDetail).toHaveBeenCalled());
    unmount();

    await act(async () => {
      rejectFetch(new Error('boom'));
      await Promise.resolve();
    });
  });
});
