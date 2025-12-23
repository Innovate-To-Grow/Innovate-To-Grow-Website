import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { fetchPageContent, type PageContent as PageContentType } from '../../services/api';
import './PageContent.css';

export const PageContent = () => {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<PageContentType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadPage = async (pageSlug: string) => {
      setLoading(true);
      setError(null);
      try {
        const pageData = await fetchPageContent(pageSlug);
        setPage(pageData);
        
        // Handle external URL redirect
        if (pageData?.page_type === 'external' && pageData.external_url) {
          window.location.href = pageData.external_url;
        }
      } catch (err) {
        setError('Failed to load page content');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    if (slug) {
      loadPage(slug);
    }
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

  if (!page) {
    return null;
  }

  return (
    <div className="page-content-container">
      <div className="page-content">
        <h1>{page.title}</h1>
        
        {/* Regular Page: Render HTML content */}
        {page.page_type === 'page' && page.page_body && (
          <div 
            className="page-body" 
            dangerouslySetInnerHTML={{ __html: page.page_body }} 
          />
        )}
        
        {/* External URL: Show redirect message */}
        {page.page_type === 'external' && (
          <div className="external-redirect">
            <p>Redirecting to external URL...</p>
            <p>
              If you are not redirected,{' '}
              <a href={page.external_url ?? '#'} target="_blank" rel="noopener noreferrer">
                click here
              </a>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
