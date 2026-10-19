import {useMatches} from 'react-router';
import {usePageTitle} from '@/hooks/usePageTitle';

export interface RouteHandle {
  /** Fixed name of the page, shown in the browser tab as "<title> | Innovate to Grow". */
  title?: string;
}

/**
 * Sets the tab title from the deepest matched route's `handle.title`. Rendered before the layout,
 * so its effect runs before the page's own: a page that names itself from its data (CMS pages,
 * news stories, projects) still has the last word.
 */
export const RouteDocumentTitle = () => {
  const title = useMatches()
    .map((match) => (match.handle as RouteHandle | undefined)?.title)
    .filter(Boolean)
    .at(-1);
  usePageTitle(title);
  return null;
};
