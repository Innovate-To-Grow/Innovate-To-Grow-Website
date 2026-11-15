import {cleanup, fireEvent, render, screen} from '@testing-library/react';
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
    expect(screen.getByText('Ada Lovelace').closest('p')).toHaveClass('itg-page-meta', 'news-detail-meta');
    expect(screen.getByRole('heading', {name: 'Detail Article', level: 1})).toHaveClass('itg-page-title');
    expect(screen.getByTestId('safe-html')).toHaveTextContent('Full body.');
    expect(screen.queryByText('A summary.')).toBeNull();
    const source = screen.getByRole('link', {name: 'View original article'});
    expect(source.getAttribute('href')).toBe('https://example.com/detail');
    expect(source).toHaveClass('itg-btn', 'itg-btn-outline');
    expect(screen.getAllByRole('link', {name: /back to news/i})).toHaveLength(1);
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
    expect(document.querySelector('.news-detail-meta-separator')).toBeNull();
    expect(screen.queryByTestId('safe-html')).toBeNull();
    expect(screen.getByText('A summary.')).toBeInTheDocument();
  });

  it('leaves out an author that is an account name rather than a byline', async () => {
    vi.mocked(fetchNewsDetail).mockResolvedValue(article({author: 'jdoe3'}));

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    expect(await screen.findByRole('heading', {name: 'Detail Article'})).toBeInTheDocument();
    expect(screen.queryByText('jdoe3')).toBeNull();
    expect(document.querySelector('.news-detail-meta-separator')).toBeNull();
  });

  it('drops the hero figure when its image fails to load', async () => {
    vi.mocked(fetchNewsDetail).mockResolvedValue(article());

    renderPage('/news/11111111-1111-4111-8111-111111111111');

    fireEvent.error(await screen.findByAltText('Detail Article'));

    expect(screen.queryByAltText('Detail Article')).toBeNull();
    expect(screen.queryByText('Hero caption')).toBeNull();
  });
});
