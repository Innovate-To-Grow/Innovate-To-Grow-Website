import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchHomeContent, type HomeContent } from '../services/api';
import { fetchLatestNews, type NewsArticle } from '../services/api/news';
import { GrapesJSRenderer } from '../components/PageContent/GrapesJSRenderer';
import './Home.css';

export const Home = () => {
  const [homeContent, setHomeContent] = useState<HomeContent | null>(null);
  const [latestNews, setLatestNews] = useState<NewsArticle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [content, news] = await Promise.all([
          fetchHomeContent(),
          fetchLatestNews().catch(() => null),
        ]);
        setHomeContent(content);
        setLatestNews(news);
      } catch (err) {
        setError('Unable to load home page content.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  if (loading) {
    return (
      <div className="home-container">
        <div className="home-state">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="home-container">
        <div className="home-state home-error">{error}</div>
      </div>
    );
  }

  if (!homeContent) {
    return null;
  }

  return (
    <div className="home-container">
      <div className="home-content">
        <GrapesJSRenderer html={homeContent.html} css={homeContent.css} slug="home" className="home-grapesjs" />
      </div>
      {latestNews && (
        <div className="home-latest-news">
          <h2 className="home-latest-news-heading">Latest News</h2>
          <Link
            to={`/news/${latestNews.id}`}
            className="home-news-card"
          >
            {latestNews.image_url && (
              <img
                src={latestNews.image_url}
                alt={latestNews.title}
                className="home-news-card-image"
                loading="lazy"
              />
            )}
            <div className="home-news-card-body">
              <h3 className="home-news-card-title">{latestNews.title}</h3>
              <time className="home-news-card-date">
                {new Date(latestNews.published_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </time>
              {latestNews.summary && <p className="home-news-card-summary">{latestNews.summary}</p>}
            </div>
          </Link>
          <Link to="/news" className="home-news-view-all">View all news &rarr;</Link>
        </div>
      )}
    </div>
  );
};
