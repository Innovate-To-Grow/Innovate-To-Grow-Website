import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router';

import { NotFoundPage } from '@/routes/NotFoundPage';
import { BlockRenderer } from './BlockRenderer';
import {
  clearCMSRouteRedirectChain,
  performCMSRouteRedirect,
} from './cmsRouteRedirect';
import { useCMSPage } from './useCMSPage';

function formatExpiryTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

interface CMSPageComponentProps {
  routeOverride?: string;
}

export const CMSPageComponent = ({routeOverride}: CMSPageComponentProps) => {
  const location = useLocation();
  const route = routeOverride || location.pathname;
  const searchParams = new URLSearchParams(location.search);
  const preview = searchParams.has('cms_preview');
  const hasPreviewToken = searchParams.has('cms_preview_token');

  const { page, redirectTo, loading, error, isLivePreview, retry } = useCMSPage(route, preview);
  const [showPreviewModal, setShowPreviewModal] = useState(isLivePreview);
  const [redirectFailure, setRedirectFailure] = useState<{
    key: string;
    kind: 'not_found' | 'error';
  } | null>(null);
  const redirectAttemptRef = useRef<{
    key: string;
    failure: 'not_found' | 'error' | null;
  } | null>(null);
  const redirectKey = redirectTo ? `${route}\n${redirectTo}` : null;
  const currentRedirectFailure = redirectFailure?.key === redirectKey
    ? redirectFailure.kind
    : null;

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

  useEffect(() => {
    if (
      !redirectTo
      || !redirectKey
      || preview
      || hasPreviewToken
      || isLivePreview
    ) {
      return;
    }

    let cancelled = false;
    const publishFailure = (kind: 'not_found' | 'error') => {
      queueMicrotask(() => {
        if (!cancelled) {
          setRedirectFailure({key: redirectKey, kind});
        }
      });
    };

    const previousAttempt = redirectAttemptRef.current;
    if (previousAttempt?.key === redirectKey) {
      if (previousAttempt.failure) {
        publishFailure(previousAttempt.failure);
      }
    } else {
      try {
        const result = performCMSRouteRedirect(redirectTo);
        const failure = result === 'redirected' ? null : 'not_found';
        redirectAttemptRef.current = {key: redirectKey, failure};
        if (failure) publishFailure(failure);
      } catch {
        redirectAttemptRef.current = {key: redirectKey, failure: 'error'};
        publishFailure('error');
      }
    }

    return () => {
      cancelled = true;
    };
  }, [redirectTo, redirectKey, preview, hasPreviewToken, isLivePreview]);

  // A successfully loaded destination ends the tab-scoped redirect chain. A
  // later, independent visit to the same legacy URL must be allowed to start a
  // fresh redirect.
  useEffect(() => {
    if (page && !redirectTo && !preview && !hasPreviewToken && !isLivePreview) {
      clearCMSRouteRedirectChain();
    }
  }, [page, redirectTo, preview, hasPreviewToken, isLivePreview]);

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
    return (
      <div className="cms-page-shell cms-page-loading" aria-busy="true">
        <div role="status" aria-label="Loading page content" className="cms-page-status">
          <span className="cms-page-status-text">Loading page content</span>
        </div>
        <div className="cms-page-skeleton cms-page-skeleton-hero" aria-hidden="true" />
        <div className="cms-page-skeleton" aria-hidden="true" />
        <div className="cms-page-skeleton" aria-hidden="true" />
      </div>
    );
  }

  if (!isLivePreview && currentRedirectFailure === 'not_found') {
    return <NotFoundPage />;
  }

  if (!isLivePreview && currentRedirectFailure === 'error') {
    return (
      <div className="cms-page-error">
        <p>Something went wrong loading this page.</p>
      </div>
    );
  }

  if (!isLivePreview && redirectTo) {
    return <div className="cms-page-loading" />;
  }

  if (!isLivePreview && error === 'not_found') {
    return <NotFoundPage />;
  }

  if (!isLivePreview && error) {
    return (
      <div className="cms-page-error" role="alert">
        <p>Something went wrong loading this page.</p>
        <button type="button" onClick={retry}>Try again</button>
      </div>
    );
  }

  if (!isLivePreview && !page) {
    return <NotFoundPage />;
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
        {page && (
          <BlockRenderer
            blocks={page.blocks}
            prioritizeFirstImage={route === '/' || route === '/home'}
          />
        )}
      </div>
    </>
  );
};
