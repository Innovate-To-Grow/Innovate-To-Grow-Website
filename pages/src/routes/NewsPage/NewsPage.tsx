import { useState, useEffect } from 'react';
import { Link } from 'react-router';
import { fetchNews, type NewsArticle, type PaginatedResponse } from '@/features/news';

const PAGE_SIZE = 12;

type PageItem = number | 'gap';

/** First, last, and the pages around the current one; gaps collapse into an ellipsis. */
function paginationItems(current: number, total: number): PageItem[] {
  const pages = [1, current - 1, current, current + 1, total]
    .filter((value, index, all) => value >= 1 && value <= total && all.indexOf(value) === index)
    .sort((a, b) => a - b);
  const items: PageItem[] = [];
  let previous = 0;
  for (const value of pages) {
    if (value - previous === 2) {
      items.push(previous + 1);
    } else if (value - previous > 2) {
      items.push('gap');
    }
    items.push(value);
    previous = value;
  }
  return items;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

const NewsCard = ({ article }: { article: NewsArticle }) => (
  <li className="news-card">
    {article.image_url ? (
      <img src={article.image_url} alt="" className="news-card-image" loading="lazy" />
    ) : (
      <div className="news-card-image news-card-placeholder" aria-hidden="true" />
    )}
    <div className="news-card-body">
      <h2 className="news-card-title">
        <Link to={`/news/${article.id}`} className="news-card-link">
          {article.title}
        </Link>
      </h2>
      <p className="itg-page-meta news-card-date">
        <time dateTime={article.published_at}>{formatDate(article.published_at)}</time>
      </p>
      {article.summary && <p className="news-card-summary">{article.summary}</p>}
    </div>
  </li>
);

export const NewsPage = () => {
  const [data, setData] = useState<PaginatedResponse<NewsArticle> | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchNews(page);
        setData(result);
      } catch {
        setError('Unable to load news.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [page]);

  let body;
  if (loading) {
    body = <p className="news-state" role="status">Loading...</p>;
  } else if (error) {
    body = <p className="news-state news-error itg-error" role="alert">{error}</p>;
  } else if (!data || data.results.length === 0) {
    body = <p className="news-state">No news articles available.</p>;
  } else {
    const totalPages = Math.ceil(data.count / PAGE_SIZE);
    body = (
      <>
        <ul className="news-list">
          {data.results.map((article) => (
            <NewsCard key={article.id} article={article} />
          ))}
        </ul>
        {totalPages > 1 && (
          <nav className="itg-pagination news-pagination" aria-label="News pages">
            <button
              type="button"
              className="itg-pagination-link news-pagination-btn news-pagination-prev"
              disabled={!data.previous}
              onClick={() => setPage((p) => p - 1)}
            >
              <span aria-hidden="true">‹&nbsp;</span>Previous
            </button>
            <ul className="news-pagination-pages">
              {paginationItems(page, totalPages).map((item, index) => (
                <li key={item === 'gap' ? `gap-${index}` : item}>
                  {item === 'gap' ? (
                    <span className="itg-pagination-gap news-pagination-gap" aria-hidden="true">…</span>
                  ) : item === page ? (
                    <span className="itg-pagination-link news-pagination-current" aria-current="page">
                      <span className="sr-only">Page </span>{item}
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="itg-pagination-link news-pagination-page"
                      aria-label={`Page ${item}`}
                      onClick={() => setPage(item)}
                    >
                      {item}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <span className="news-pagination-info">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="itg-pagination-link news-pagination-btn news-pagination-next"
              disabled={!data.next}
              onClick={() => setPage((p) => p + 1)}
            >
              Next<span aria-hidden="true">&nbsp;›</span>
            </button>
          </nav>
        )}
      </>
    );
  }

  return (
    <div className="news-page">
      <h1 className="itg-page-title news-page-title">News</h1>
      {body}
    </div>
  );
};
