import {useLayoutEffect, useRef} from 'react';

export const MERGED_RESULTS_ID = 'past-projects-saved-results';

export interface ScrollAnchor {
  element: Element;
  /** Where the element sat in the viewport just before the change. */
  top: number;
}

const visibleAnchor = (element: Element): ScrollAnchor | null => {
  const {top, bottom} = element.getBoundingClientRect();
  return bottom > 0 && top < window.innerHeight ? {element, top} : null;
};

// What to keep in place while the saved results change: when the user is working in the saved results
// (naming the list, writing the note, checking rows), the element they are in, since the save can add a row
// above it; otherwise the search table holding focus, else the one that saved. Only while it is on screen:
// off-screen, the browser's own scroll anchoring keeps what they are looking at where it is.
export const findScrollAnchor = (tableId: string): ScrollAnchor | null => {
  const active = document.activeElement;
  if (active?.closest(`#${MERGED_RESULTS_ID}`)) {
    return visibleAnchor(active);
  }
  const candidates = [
    active?.closest('[data-search-table-id]'),
    document.querySelector(`[data-search-table-id="${tableId}"]`),
  ];
  for (const element of candidates) {
    const anchor = element ? visibleAnchor(element) : null;
    if (anchor) {
      return anchor;
    }
  }
  return null;
};

/**
 * Keep an anchor (set just before a change to `dependency`) where it was on screen. The saved results
 * card mounts (or grows) above the search tables, and the browser's scroll anchoring only compensates when
 * its anchor sits below that change. Reading the position forces layout, so any correction the browser made
 * is already applied and only what is left is scrolled away.
 */
export function useKeepScrollAnchor(dependency: unknown) {
  const pendingAnchor = useRef<ScrollAnchor | null>(null);

  useLayoutEffect(() => {
    const anchor = pendingAnchor.current;
    pendingAnchor.current = null;
    if (!anchor?.element.isConnected) {
      return;
    }
    const shift = anchor.element.getBoundingClientRect().top - anchor.top;
    if (Math.abs(shift) > 1) {
      window.scrollBy(0, shift);
    }
  }, [dependency]);

  return pendingAnchor;
}

/** Scroll to the saved results and move keyboard focus along with the view. */
export const scrollToMergedResults = () => {
  const section = document.getElementById(MERGED_RESULTS_ID);
  if (!section) {
    return;
  }
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  section.scrollIntoView?.({behavior: reduceMotion ? 'auto' : 'smooth', block: 'start'});
  section.querySelector<HTMLElement>('.project-grid-card-title')?.focus({preventScroll: true});
};
