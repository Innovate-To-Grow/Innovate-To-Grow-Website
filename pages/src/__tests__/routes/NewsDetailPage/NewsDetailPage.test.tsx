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

    expect(screen.getByRole('status')).toHaveTextContent('Loading...');
    expect(screen.getByRole('link', {name: 'Back to News'})).toHaveClass('itg-back-link');
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
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load this article.');
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

  it('names the tab after the article', async () => {
    vi.mocked(fetchNewsDetail).mockResolvedValue(article());

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    await screen.findByRole('heading', {name: 'Detail Article'});
    // usePageTitle sets the title in an effect, which can run after the heading is on screen.
    await waitFor(() => expect(document.title).toBe('Detail Article | Innovate to Grow'));
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
