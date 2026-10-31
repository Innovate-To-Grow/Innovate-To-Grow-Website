import {useEffect, useState, useSyncExternalStore} from 'react';
import {useRouteError} from 'react-router';
import {ErrorFallback} from '@/app/ErrorBoundary';
import {
  getPageReloadStatus,
  isChunkLoadError,
  isNewBuildDeployed,
  mayReloadForNewBuild,
  reloadForNewBuild,
  subscribeToPageReload,
} from '@/app/pageReload';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {usePageTitle} from '@/hooks/usePageTitle';

const CHUNK_ERROR_MESSAGE =
  "This page couldn't be loaded, most likely because the site was just updated. Reload the page to get the latest version.";
const RENDER_ERROR_MESSAGE = 'Something went wrong while showing this page. Reload the page to try again.';

interface RouteErrorPageProps {
  /**
   * True for the error element of a route that renders inside the page shell (it keeps the menu, footer and
   * content column); false for a top-level route, whose error replaces everything in #root.
   */
  inShell?: boolean;
}

/**
 * The error element of every route: whatever a page throws while loading or rendering (a route chunk
 * missing after a deploy, a render crash) ends here instead of React Router's developer screen with the
 * stack trace. A chunk that failed to load first reloads the page once onto the new build, when one is
 * deployed (the only automatic reload: other lazy imports handle their own failures).
 */
export function RouteErrorPage({inShell = true}: RouteErrorPageProps) {
  const error = useRouteError();
  const chunkError = isChunkLoadError(error);
  const reloadStatus = useSyncExternalStore(subscribeToPageReload, getPageReloadStatus);
  // The chunk error found to have no new build behind it: a reload would not bring the chunk back.
  const [noNewBuildFor, setNoNewBuildFor] = useState<unknown>(null);
  // Decided while rendering, so the error message never flashes before the check and the reload below.
  const checking = chunkError && noNewBuildFor !== error && mayReloadForNewBuild();
  const reloading = reloadStatus === 'reloading';
  usePageTitle(checking || reloading ? null : 'Something went wrong', {noindex: true});

  useEffect(() => {
    console.error('Route error:', error);
  }, [error]);

  useEffect(() => {
    if (!checking || reloading) return;
    let current = true;
    void isNewBuildDeployed().then((deployed) => {
      if (current && !(deployed && reloadForNewBuild())) setNoNewBuildFor(error);
    });
    return () => {
      current = false;
    };
  }, [checking, reloading, error]);

  if (checking || reloading) {
    return (
      <div className="page-loader" role="status">
        <LoadingIndicator label={reloading ? 'Loading the latest version of the site…' : 'Loading page…'} />
      </div>
    );
  }

  return (
    <ErrorFallback
      headingLevel="h1"
      message={chunkError ? CHUNK_ERROR_MESSAGE : RENDER_ERROR_MESSAGE}
      reloadLabel="Reload page"
      className={inShell ? '' : 'app-error-boundary'}
      focusHeading
    />
  );
}
