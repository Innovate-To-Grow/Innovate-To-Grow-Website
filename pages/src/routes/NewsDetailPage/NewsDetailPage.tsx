import '@/routes/NewsPage/news.css';
import './NewsDetailPage.css';
import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router';
import { fetchNewsDetail, type NewsArticle } from '@/features/news';
import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import { safeHref } from '@/lib/security';
import { usePageTitle } from '@/hooks/usePageTitle';

/**
 * The news feed's author field is the poster's campus account name (for example "jdoe3"), not a
 * byline. Only a value that reads like a person's name (two or more words) is shown.
 */
const isBylineName = (author: string | undefined): author is string => Boolean(author && /\S\s+\S/.test(author.trim()));

const BackToNews = () => (
  <Link to="/news" className="itg-back-link news-detail-back">
    <span aria-hidden="true">‹&nbsp;</span>Back to News
  </Link>
);

export const NewsDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const [article, setArticle] = useState<NewsArticle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  usePageTitle(article?.title || 'News');
  // The hero is hot-linked from the news source; one that fails to load is left out.
  const [failedHero, setFailedHero] = useState<string | null>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError(null);
      setArticle(null);
      try {
        const data = await fetchNewsDetail(id, controller.signal);
        if (controller.signal.aborted) return;
        setArticle(data);
      } catch {
        if (controller.signal.aborted) return;
        setError('Unable to load this article.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [id]);

  if (loading) {
    return (
      <div className="news-detail">
        <BackToNews />
        <p className="news-state" role="status">Loading...</p>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="news-detail">
        <BackToNews />
        <p className="news-state news-error itg-error" role="alert">{error || 'Article not found.'}</p>
      </div>
    );
  }

  const publishedOn = new Date(article.published_at).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <article className="news-detail">
      <BackToNews />

      <header className="news-detail-header">
        <h1 className="itg-page-title news-detail-title">{article.title}</h1>
        <p className="itg-page-meta news-detail-meta">
          {isBylineName(article.author) && (
            <>
              <span className="news-detail-author">{article.author}</span>
              <span className="news-detail-meta-separator" aria-hidden="true"> · </span>
            </>
          )}
          <time dateTime={article.published_at}>{publishedOn}</time>
        </p>
      </header>

      {article.hero_image_url && failedHero !== article.hero_image_url && (
        <figure className="news-detail-hero">
          <img
            src={article.hero_image_url}
            alt={article.title}
            width={1200}
            height={630}
            loading="lazy"
            onError={() => setFailedHero(article.hero_image_url ?? null)}
          />
          {article.hero_caption && (
            <figcaption className="news-detail-hero-caption">{article.hero_caption}</figcaption>
          )}
        </figure>
      )}

      {article.content ? (
        <SafeHtml className="news-detail-content" html={article.content} />
      ) : (
        article.summary && <p className="news-detail-content">{article.summary}</p>
      )}

      <div className="news-detail-actions">
        <a
          href={safeHref(article.source_url)}
          target="_blank"
          rel="noopener noreferrer"
          className="itg-btn itg-btn-outline news-detail-source"
        >
          View original article
        </a>
      </div>
    </article>
  );
};
