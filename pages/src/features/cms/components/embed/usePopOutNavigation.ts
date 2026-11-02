import { useCallback, useEffect, useState } from 'react';
import { NavigationType, useBlocker, type BlockerFunction } from 'react-router';

/** Whether the click that navigated still lets the page open a tab (assumed where the browser cannot tell). */
const hasUserActivation = () => window.navigator.userActivation?.isActive ?? true;

/**
 * Whether this runs inside the user's own click or key press, rather than in code resumed after one
 * (e.g. once a save request returns, when Safari's popup blocker refuses a tab though the click is recent).
 * The router asks its blockers synchronously, so a link's click event is still being dispatched here.
 */
const inUserEvent = () => window.event?.isTrusted === true;

/** ``url`` in a new tab, cut off from this frame; false when the browser would not open it. */
function openInNewTab(url: string): boolean {
  try {
    const tab = window.open(url, '_blank');
    if (!tab) return false;
    tab.opener = null;
    return true;
  } catch {
    // Firefox throws, rather than returning null, in a frame sandboxed without allow-popups.
    return false;
  }
}

/** A navigation out of the widget whose tab the browser refused, outside a click: where it went and its state. */
export interface BlockedNavigation {
  to: string;
  state: unknown;
}

/**
 * Keeps the widget in its frame. `<base target="_blank">` pops plain links out, but router links and
 * `navigate()` would swap the widget for another site page inside a chromeless frame that no longer
 * reports its height. A navigation to another path opens that page in a new tab instead; search and
 * hash changes stay, as the embedded pages keep their own state there.
 *
 * A tab the browser refuses inside the user's own click means the frame opens no tabs at all (a partner
 * sandboxed it without allow-popups), so the page opens in the frame after all rather than the click
 * doing nothing. Any other refusal (e.g. after a slow save) is handed back for the caller to offer as a
 * router link, whose click comes through here again.
 */
export function usePopOutNavigation(): BlockedNavigation | null {
  const [blocked, setBlocked] = useState<BlockedNavigation | null>(null);

  const leavesEmbed = useCallback<BlockerFunction>(({currentLocation, nextLocation, historyAction}) => {
    if (historyAction === NavigationType.Pop || nextLocation.pathname === currentLocation.pathname) return false;
    const {pathname, search, hash, state} = nextLocation;
    const to = `${pathname}${search}${hash}`;
    const activated = hasUserActivation();
    // Opened here, still inside the click that navigated, so popup blockers let it through.
    if (activated && openInNewTab(new URL(to, window.location.origin).href)) {
      setBlocked(null);
      return true;
    }
    if (activated && inUserEvent()) {
      setBlocked(null);
      return false;
    }
    setBlocked({to, state});
    return true;
  }, []);

  const blocker = useBlocker(leavesEmbed);
  useEffect(() => {
    if (blocker.state === 'blocked') blocker.reset();
  }, [blocker]);

  return blocked;
}
