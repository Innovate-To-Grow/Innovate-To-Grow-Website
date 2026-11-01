import {useEffect} from 'react';
import {claimDocumentHead, setOpenGraphTitle, type HeadClaimLevel} from './documentHead';

/** The site name every page title ends with, after the page's own name. */
export const SITE_NAME = 'Innovate to Grow';

export const formatDocumentTitle = (pageTitle: string): string => `${pageTitle} | ${SITE_NAME}`;

export interface PageMetaOptions {
  /** One or two sentences for search results; blank keeps the route's or the site's description. */
  description?: string | null;
  /** Keeps the page out of search indexes: not-found and unavailable states, user-made pages. */
  noindex?: boolean;
}

/** usePageTitle with the claim level: route defaults (RouteDocumentTitle) lose to the page's own. */
export function useDocumentHead(
  pageTitle: string | null | undefined,
  {description, noindex = false}: PageMetaOptions,
  level: HeadClaimLevel,
): void {
  useEffect(() => {
    const trimmed = pageTitle?.trim();
    if (!trimmed) return;
    document.title = formatDocumentTitle(trimmed);
    setOpenGraphTitle(trimmed);
  }, [pageTitle]);

  useEffect(() => {
    if (!description?.trim() && !noindex) return;
    return claimDocumentHead({description, noindex}, level);
  }, [description, noindex, level]);
}

/**
 * Names the browser tab after the page. Pages whose title comes from their data (a news story, a
 * project) call this with that data; pages with a fixed name get it from their route's `handle`.
 * A blank title leaves the current one in place. `options` adds the page's meta description and marks
 * error and not-found states noindex (both are withdrawn when the page unmounts).
 */
export function usePageTitle(pageTitle: string | null | undefined, options: PageMetaOptions = {}): void {
  useDocumentHead(pageTitle, options, 'page');
}
