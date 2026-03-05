import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchNews, type NewsArticle, type PaginatedResponse } from '../services/api/news';
import './NewsPage.css';

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

  if (loading) {
    return (
      <div className="news-page">
        <div className="news-state">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="news-page">
        <div className="news-state news-error">{error}</div>
      </div>
    );
  }

  if (!data || data.results.length === 0) {
    return (
      <div className="news-page">
        <h1 className="news-page-title">News</h1>
        <div className="news-state">No news articles available.</div>
      </div>
    );
  }

  const totalPages = Math.ceil(data.count / 12);

  return (
    <div className="news-page">
      <h1 className="news-page-title">News</h1>
      <div className="news-grid">
        {data.results.map((article) => (
          <Link
            key={article.id}
            to={`/news/${article.id}`}
            className="news-card"
          >
            {article.image_url ? (
              <img
                src={article.image_url}
                alt={article.title}
                className="news-card-image"
                loading="lazy"
              />
            ) : (
              <div className="news-card-image news-card-placeholder" />
            )}
            <div className="news-card-body">
              <h2 className="news-card-title">{article.title}</h2>
              <time className="news-card-date">
                {new Date(article.published_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </time>
              {article.summary && <p className="news-card-summary">{article.summary}</p>}
            </div>
          </Link>
        ))}
      </div>
      {totalPages > 1 && (
        <div className="news-pagination">
          <button
            className="news-pagination-btn"
            disabled={!data.previous}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="news-pagination-info">
            Page {page} of {totalPages}
          </span>
          <button
            className="news-pagination-btn"
            disabled={!data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
