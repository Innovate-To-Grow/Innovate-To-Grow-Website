import {useEffect} from 'react';

/** The site name every page title ends with, after the page's own name. */
export const SITE_NAME = 'Innovate to Grow';

export const formatDocumentTitle = (pageTitle: string): string => `${pageTitle} | ${SITE_NAME}`;

/**
 * Names the browser tab after the page. Pages whose title comes from their data (a news story, a
 * project) call this with that data; pages with a fixed name get it from their route's `handle`.
 * A blank title leaves the current one in place.
 */
export function usePageTitle(pageTitle: string | null | undefined): void {
  useEffect(() => {
    const trimmed = pageTitle?.trim();
    if (trimmed) document.title = formatDocumentTitle(trimmed);
  }, [pageTitle]);
}
