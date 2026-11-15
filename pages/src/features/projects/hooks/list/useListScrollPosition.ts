import {useLayoutEffect, useRef, useState} from 'react';
import {useLocation, useNavigationType} from 'react-router';

/** Where the visitor had scrolled each list visit (by history entry), for coming back to it. */
const savedPositions = new Map<string, number>();
const MAX_SAVED_POSITIONS = 50;

const savePosition = (entryKey: string, scrollY: number) => {
  savedPositions.delete(entryKey);
  savedPositions.set(entryKey, scrollY);
  if (savedPositions.size > MAX_SAVED_POSITIONS) {
    savedPositions.delete(savedPositions.keys().next().value as string);
  }
};

/**
 * Scroll for a list page whose rows load after it mounts. Opened by a link it starts at the top (the router keeps
 * the previous page's scroll otherwise, which opened the list mid-page). Come back to with Back or Forward, it
 * returns to where the visitor left it once `ready` (the rows are shown): before that the page is too short to
 * scroll there.
 */
export function useListScrollPosition(ready: boolean) {
  const location = useLocation();
  const navigationType = useNavigationType();
  const [restoreTo] = useState(() => (navigationType === 'POP' ? savedPositions.get(location.key) : undefined));
  const [startedAtTop] = useState(() => navigationType !== 'POP');
  const restoredRef = useRef(false);

  useLayoutEffect(() => {
    if (startedAtTop) window.scrollTo(0, 0);
  }, [startedAtTop]);

  useLayoutEffect(() => {
    if (!ready || restoreTo === undefined || restoredRef.current) return;
    restoredRef.current = true;
    window.scrollTo(0, restoreTo);
  }, [ready, restoreTo]);

  // Saved under the history entry's current key: the list rewrites its entry (and so its key) as its filters change.
  // The position is the last one a scroll event reported, not scrollY at leave time: by the time the list's
  // effects are cleaned up the page may already have shrunk to the next page's height, which clamps scrollY.
  useLayoutEffect(() => {
    const entryKey = location.key;
    let lastScrollY = window.scrollY;
    const record = () => {
      lastScrollY = window.scrollY;
    };
    window.addEventListener('scroll', record, {passive: true});
    return () => {
      window.removeEventListener('scroll', record);
      savePosition(entryKey, lastScrollY);
    };
  }, [location.key]);
}
