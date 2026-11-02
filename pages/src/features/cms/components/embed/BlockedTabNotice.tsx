import { useEffect, useRef } from 'react';
import { Link } from 'react-router';
import type { BlockedNavigation } from './usePopOutNavigation';

/**
 * Offers the page a navigation out of the widget could not open in a new tab. The region stays rendered,
 * empty, so screen readers announce the link when it fills in. The frame is as tall as the widget, so
 * the link at its top may sit far off screen from the control that asked for the page: it takes focus
 * (scrolling it into view) while the user is in the widget. It is a router link, so its click comes
 * back through `usePopOutNavigation` with the navigation's state, now with a click to open the tab.
 */
export function BlockedTabNotice({blocked}: {blocked: BlockedNavigation | null}) {
  const linkRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (blocked && document.hasFocus()) linkRef.current?.focus();
  }, [blocked]);

  return (
    <div role="status">
      {blocked ? (
        <p className="cms-embed-message">
          <Link ref={linkRef} to={blocked.to} state={blocked.state}>
            Open the page in a new tab
          </Link>
        </p>
      ) : null}
    </div>
  );
}
