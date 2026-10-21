import {useState} from 'react';
import {useLocation} from 'react-router';

import {NotFoundPage} from '@/components/NotFoundPage';
import {BlockRenderer} from './BlockRenderer';
import {CMSPageError, CMSPageLoading} from './page/CMSPageStatus';
import {LivePreviewNotice} from './page/LivePreviewNotice';
import {useCMSPageDocument} from './page/useCMSPageDocument';
import {useCMSRouteRedirect} from './page/useCMSRouteRedirect';
import {cmsPageClassName} from './pageClassName';
import {useCMSPage} from './useCMSPage';

interface FallbackState {
  redirectFailure: ReturnType<typeof useCMSRouteRedirect>;
  redirectTo: string | null | undefined;
  error: ReturnType<typeof useCMSPage>['error'];
  page: ReturnType<typeof useCMSPage>['page'];
  retry: () => void;
}

/** What a published page shows instead of its blocks: a redirect in flight, not-found, or an error. */
const nonPreviewFallback = ({redirectFailure, redirectTo, error, page, retry}: FallbackState) => {
  if (redirectFailure === 'error') return <CMSPageError />;
  if (redirectFailure === 'not_found') return <NotFoundPage />;
  if (redirectTo) return <div className="cms-page-loading" />;
  if (error === 'not_found' || (!error && !page)) return <NotFoundPage />;
  if (error) return <CMSPageError onRetry={retry} />;
  return null;
};

interface CMSPageComponentProps {
  routeOverride?: string;
}

/**
 * Renders the CMS page for the current route: follows its redirect, shows its blocks, and — in an admin
 * live preview — the preview notice (preview pages never redirect and render even while erroring).
 */
export const CMSPageComponent = ({routeOverride}: CMSPageComponentProps) => {
  const location = useLocation();
  const route = routeOverride || location.pathname;
  const searchParams = new URLSearchParams(location.search);
  const preview = searchParams.has('cms_preview');
  const hasPreviewToken = searchParams.has('cms_preview_token');

  const {page, redirectTo, loading, error, isLivePreview, retry} = useCMSPage(route, preview);
  const [showPreviewModal, setShowPreviewModal] = useState(isLivePreview);
  const redirectFailure = useCMSRouteRedirect(route, redirectTo, {
    previewing: preview || hasPreviewToken || isLivePreview,
    page,
  });
  const {contentRef, needsFallbackTitle} = useCMSPageDocument(page, isLivePreview);

  if (loading) {
    return <CMSPageLoading />;
  }
  const fallback = isLivePreview ? null : nonPreviewFallback({redirectFailure, redirectTo, error, page, retry});
  if (fallback) return fallback;

  return (
    <>
      {isLivePreview ? (
        <LivePreviewNotice expiresAt={page?.expires_at} open={showPreviewModal} onOpenChange={setShowPreviewModal} />
      ) : null}
      {page && needsFallbackTitle ? <h1 className="sr-only">{page.title}</h1> : null}
      <div ref={contentRef} className={cmsPageClassName(page?.page_css_class)}>
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
