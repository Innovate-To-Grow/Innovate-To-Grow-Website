import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchNewsDetail, type NewsArticle } from '../../services/api/news';
import './NewsDetailPage.css';

export const NewsDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const [article, setArticle] = useState<NewsArticle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchNewsDetail(id);
        setArticle(data);
      } catch {
        setError('Unable to load this article.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  if (loading) {
    return (
      <div className="news-detail">
        <div className="news-state">Loading...</div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="news-detail">
        <Link to="/news" className="news-detail-back">&larr; Back to News</Link>
        <div className="news-state news-error">{error || 'Article not found.'}</div>
      </div>
    );
  }

  return (
    <div className="news-detail">
      <Link to="/news" className="news-detail-back">&larr; Back to News</Link>

      {article.hero_image_url && (
        <figure className="news-detail-hero">
          <img src={article.hero_image_url} alt={article.title} />
          {article.hero_caption && (
            <figcaption className="news-detail-hero-caption">{article.hero_caption}</figcaption>
          )}
        </figure>
      )}

      <h1 className="news-detail-title">{article.title}</h1>
      <div className="news-detail-meta">
        {article.author && <span className="news-detail-author">{article.author}</span>}
        <time>
          {new Date(article.published_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}
        </time>
      </div>
      {article.content ? (
        <div
          className="news-detail-content"
          dangerouslySetInnerHTML={{ __html: article.content }}
        />
      ) : (
        article.summary && <p className="news-detail-content">{article.summary}</p>
      )}
      <a
        href={article.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="news-detail-source"
      >
        View original article
      </a>
    </div>
  );
};
