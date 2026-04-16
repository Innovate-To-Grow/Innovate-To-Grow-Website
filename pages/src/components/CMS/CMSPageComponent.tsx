import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { NotFoundPage } from '../../pages/NotFoundPage';
import { BlockRenderer } from './BlockRenderer';
import { useCMSPage } from './useCMSPage';

function formatExpiryTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// CMS block styling is now served from the backend via StyleSheet model.
// Design tokens and stylesheets are injected by LayoutProvider.
// Page-specific CSS is served via the page_css field on CMSPage.

interface CMSPageComponentProps {
  routeOverride?: string;
}

export const CMSPageComponent: React.FC<CMSPageComponentProps> = ({routeOverride}) => {
  const location = useLocation();
  const route = routeOverride || location.pathname;
  const preview = new URLSearchParams(location.search).has('cms_preview');

  const { page, loading, error, isLivePreview } = useCMSPage(route, preview);
  const [showPreviewModal, setShowPreviewModal] = useState(isLivePreview);

  const expiresAt = page?.expires_at;
  const expiryDisplay = useMemo(() => {
    if (!expiresAt) return null;
    return formatExpiryTime(expiresAt);
  }, [expiresAt]);

  useEffect(() => {
    if (page?.title) {
      const suffix = isLivePreview ? ' [Live Preview]' : '';
      document.title = `${page.title}${suffix} | Innovate to Grow`;
    }
  }, [page?.title, isLivePreview]);

  // Inject per-page CSS from the backend
  useEffect(() => {
    if (!page?.page_css) return;
    let el = document.getElementById('itg-page-css');
    if (!el) {
      el = document.createElement('style');
      el.id = 'itg-page-css';
      document.head.appendChild(el);
    }
    el.textContent = page.page_css;
    return () => {
      if (el) el.textContent = '';
    };
  }, [page?.page_css]);

  if (loading) {
    return <div className="cms-page-loading" />;
  }

  if (!isLivePreview && (error === 'not_found' || !page)) {
    return <NotFoundPage />;
  }

  if (!isLivePreview && error) {
    return (
      <div className="cms-page-error">
        <p>Something went wrong loading this page.</p>
      </div>
    );
  }

  return (
    <>
      {isLivePreview && showPreviewModal && (
        <div className="cms-live-preview-overlay" onClick={() => setShowPreviewModal(false)}>
          <div className="cms-live-preview-modal" onClick={(e) => e.stopPropagation()}>
            <span className="cms-live-preview-modal-dot" />
            <p className="cms-live-preview-modal-text">
              Previewing This Page With Content Management System with Admin Permission
            </p>
            {expiryDisplay && (
              <p className="cms-live-preview-modal-expiry">Expires at {expiryDisplay}</p>
            )}
            <button className="cms-live-preview-modal-close" onClick={() => setShowPreviewModal(false)}>
              OK
            </button>
          </div>
        </div>
      )}
      {isLivePreview && !showPreviewModal && (
        <div className="cms-live-preview-badge" onClick={() => setShowPreviewModal(true)}>
          <span className="cms-live-preview-modal-dot" />
          <span>CMS Preview</span>
          {expiryDisplay && (
            <span className="cms-live-preview-badge-expiry">Expires {expiryDisplay}</span>
          )}
        </div>
      )}
      <div className={page?.page_css_class || 'cms-page'}>
        {page && <BlockRenderer blocks={page.blocks} />}
      </div>
    </>
  );
};
