import { useCallback, useEffect, useState } from 'react';
import { NavigationType, useBlocker, type BlockerFunction } from 'react-router';

/** Whether the click that navigated still lets the page open a tab (assumed where the browser cannot tell). */
const hasUserActivation = () => window.navigator.userActivation?.isActive ?? true;

/** ``url`` in a new tab, cut off from this frame; false when the browser would not open it. */
function openInNewTab(url: string): boolean {
  const tab = window.open(url, '_blank');
  if (!tab) return false;
  tab.opener = null;
  return true;
}

/**
 * Keeps the widget in its frame. `<base target="_blank">` pops plain links out, but router links and
 * `navigate()` would swap the widget for another site page inside a chromeless frame that no longer
 * reports its height. A navigation to another path opens that page in a new tab instead; search and
 * hash changes stay, as the embedded pages keep their own state there.
 *
 * Returns the URL a blocked tab was meant to show (the caller offers it as a link) and a way to drop it.
 */
export function usePopOutNavigation(): {blockedUrl: string | null; clearBlockedUrl: () => void} {
  const [blockedUrl, setBlockedUrl] = useState<string | null>(null);

  const leavesEmbed = useCallback<BlockerFunction>(({currentLocation, nextLocation, historyAction}) => {
    if (historyAction === NavigationType.Pop || nextLocation.pathname === currentLocation.pathname) return false;
    const {pathname, search, hash} = nextLocation;
    const url = new URL(`${pathname}${search}${hash}`, window.location.origin).href;
    // Opened here, still inside the click that navigated, so popup blockers let it through.
    setBlockedUrl(hasUserActivation() && openInNewTab(url) ? null : url);
    return true;
  }, []);

  const blocker = useBlocker(leavesEmbed);
  useEffect(() => {
    if (blocker.state === 'blocked') blocker.reset();
  }, [blocker]);

  const clearBlockedUrl = useCallback(() => setBlockedUrl(null), []);
  return {blockedUrl, clearBlockedUrl};
}
