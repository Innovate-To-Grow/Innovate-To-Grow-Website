import {useEffect} from 'react';
import {useLocation, useMatches} from 'react-router';
import {setCanonicalUrl} from '@/lib/documentHead';
import {useDocumentHead} from '@/hooks/usePageTitle';

export interface RouteHandle {
  /** Fixed name of the page, shown in the browser tab as "<title> | Innovate to Grow". */
  title?: string;
  /** The page's meta description, until the page states its own. */
  description?: string;
  /** Keeps every page under this route out of search indexes (user-made content). */
  noindex?: boolean;
}

/**
 * Sets the tab title, meta description and robots tag from the matched routes' `handle`s (the deepest
 * title and description win; any noindex applies), and the canonical URL from the location. Rendered
 * before the layout, so its effects run before the page's own: a page that names or describes itself
 * from its data (CMS pages, news stories, projects) still has the last word.
 */
export const RouteDocumentTitle = () => {
  const handles = useMatches().map((match) => match.handle as RouteHandle | undefined);
  const title = handles.map((handle) => handle?.title).filter(Boolean).at(-1);
  const description = handles.map((handle) => handle?.description).filter(Boolean).at(-1);
  const noindex = handles.some((handle) => handle?.noindex);
  useDocumentHead(title, {description, noindex}, 'route');

  const {pathname} = useLocation();
  useEffect(() => {
    setCanonicalUrl(new URL(pathname, window.location.origin).href);
  }, [pathname]);
  return null;
};
