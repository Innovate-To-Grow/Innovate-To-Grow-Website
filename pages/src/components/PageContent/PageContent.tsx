import { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { isAxiosError } from 'axios';
import { fetchPageContent, type PageContent as PageContentType } from '../../services/api';
import { GrapesJSRenderer } from './GrapesJSRenderer';
import './PageContent.css';

type PageRouteParams = {
  slug?: string;
  '*': string | undefined;
};

const normalizeSlug = (value?: string) => {
  if (!value) return undefined;
  return value.replace(/^\/+|\/+$/g, '');
};

export const PageContent = () => {
  const params = useParams<PageRouteParams>();
  const slug = normalizeSlug(params['*'] ?? params.slug);
  const [page, setPage] = useState<PageContentType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    const loadPage = async (pageSlug: string) => {
      setLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const pageData = await fetchPageContent(pageSlug);
        setPage(pageData);
      } catch (err) {
        if (isAxiosError(err) && err.response?.status === 404) {
          setPage(null);
          setNotFound(true);
        } else {
          setError('Failed to load page content');
          console.error(err);
        }
      } finally {
        setLoading(false);
      }
    };

    if (!slug) {
      setPage(null);
      setError(null);
      setNotFound(true);
      setLoading(false);
      return;
    }

    loadPage(slug);
  }, [slug]);

  if (loading) {
    return (
      <div className="page-content-container">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-content-container">
        <div className="error">{error}</div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="page-content-container">
        <div className="page-content not-found">
          <h1>404 - Page Not Found</h1>
          <p>The page you are looking for doesn&apos;t exist or may have been moved.</p>
          <div className="not-found-actions">
            <Link to="/">Return to the homepage</Link>
          </div>
        </div>
      </div>
    );
  }

  if (!page) {
    return null;
  }

  return (
    <div className="page-content-container">
      <div className="page-content">
        <GrapesJSRenderer html={page.html} css={page.css} slug={page.slug} />
      </div>
    </div>
  );
};
