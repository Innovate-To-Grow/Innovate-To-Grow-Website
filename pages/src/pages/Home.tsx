import { useState, useEffect } from 'react';
import { fetchHomeContent, type HomeContent } from '../services/api';
import { GrapesJSRenderer } from '../components/PageContent/GrapesJSRenderer';
import './Home.css';

export const Home = () => {
  const [homeContent, setHomeContent] = useState<HomeContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHomeContent = async () => {
      setLoading(true);
      setError(null);
      try {
        const content = await fetchHomeContent();
        setHomeContent(content);
      } catch (err) {
        setError('Unable to load home page content.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadHomeContent();
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
    </div>
  );
};
