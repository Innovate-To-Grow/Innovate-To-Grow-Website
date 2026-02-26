import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { GrapesJSRenderer } from '../../components/PageContent/GrapesJSRenderer';
import { fetchPreviewByToken, type TokenPreviewResponse } from '../../services/api/preview';

import './TokenPreviewPage.css';

export const TokenPreviewPage = () => {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<TokenPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError('No preview token provided.');
      setLoading(false);
      return;
    }

    let cancelled = false;

    const loadPreview = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchPreviewByToken(token);
        if (cancelled) return;
        if (result) {
          setData(result);
        } else {
          setError('Preview link is invalid or has expired.');
        }
      } catch {
        if (!cancelled) {
          setError('Failed to load preview.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadPreview();
    return () => { cancelled = true; };
  }, [token]);

  if (loading) {
    return (
      <div className="token-preview-loading">
        <div className="token-preview-spinner" />
        <p>Loading preview...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="token-preview-error">
        <h2>Preview Unavailable</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="token-preview-container">
      <div className="token-preview-banner">
        Preview Mode — This page has not been published yet
      </div>
      <div className="token-preview-content">
        <GrapesJSRenderer
          html={data.html}
          css={data.css}
          slug={data.slug || 'preview'}
        />
      </div>
    </div>
  );
};
