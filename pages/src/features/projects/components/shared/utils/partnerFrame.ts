/**
 * The Past Projects widget on a partner's page is a frame the partner page sizes to its content, so the partner
 * page scrolls, not the frame: the frame's viewport is the whole widget, and it cannot read the partner page's
 * scroll position. These helpers place things by the part of the frame that is on the visitor's screen instead.
 */

// How long to wait for the observer, or for the partner page to resize the frame, before going on without it.
const OBSERVER_TIMEOUT_MS = 300;
const FRAME_RESIZE_TIMEOUT_MS = 1000;

const frameFitsContent = () => document.documentElement.scrollHeight <= window.innerHeight + 1;

/** Whether this page is in a frame that is as tall as its content (the partner page scrolls instead of it). */
export const isInAutoHeightFrame = () => window.parent !== window && frameFitsContent();

/**
 * Calls back once with the part of the frame's viewport on the visitor's screen (client coordinates), or with null
 * when the observer does not say in time. An IntersectionObserver can tell that much across sites. Returns a
 * cleanup that cancels a call still waiting.
 */
export function measureVisibleFramePart(callback: (visible: DOMRectReadOnly | null) => void): () => void {
  if (typeof IntersectionObserver === 'undefined') {
    callback(null);
    return () => {};
  }
  let settled = false;
  const stop = () => {
    settled = true;
    observer.disconnect();
    window.clearTimeout(timer);
  };
  const settle = (visible: DOMRectReadOnly | null) => {
    if (!settled) {
      stop();
      callback(visible);
    }
  };
  const observer = new IntersectionObserver(([entry]) => settle(entry?.intersectionRect ?? null));
  const timer = window.setTimeout(() => settle(null), OBSERVER_TIMEOUT_MS);
  observer.observe(document.documentElement);
  return stop;
}

/**
 * Scrolls a hidden box (client coordinates) into view, which scrolls the frame's ancestors as needed. The box ends
 * at the frame's bottom at the latest: one that reached past it would let the frame's own document scroll.
 */
const scrollBoxIntoView = (top: number, height: number, block: ScrollLogicalPosition) => {
  const boxTop = Math.min(top, window.innerHeight - 1);
  const probe = document.createElement('div');
  probe.style.cssText = 'position:absolute;left:0;top:0;width:1px;visibility:hidden;pointer-events:none';
  probe.style.height = `${Math.max(Math.min(height, window.innerHeight - boxTop), 1)}px`;
  document.body.append(probe);
  // Its containing block may not start at the top of the page.
  probe.style.top = `${boxTop - probe.getBoundingClientRect().top}px`;
  probe.scrollIntoView({block});
  probe.remove();
};

/**
 * Scrolls the partner page by `distance`, as `window.scrollBy` scrolls a page of its own: a box over the visible
 * part, moved by `distance`, is scrolled into view, lined up with the screen's top edge when the frame runs past
 * it, else just far enough to be all on screen. That waits until the partner page has resized the frame to its
 * new content, which can take more than one step (until then the frame's own document would scroll instead).
 * Chromium and Firefox carry scrollIntoView over to the partner page; WebKit does not scroll a page from another
 * site, so there nothing moves.
 */
export function scrollPartnerPageBy(distance: number) {
  let started = false;
  const start = () => {
    if (started) {
      return;
    }
    started = true;
    window.removeEventListener('resize', startOnceFitting);
    window.clearTimeout(timer);
    measureVisibleFramePart((visible) => {
      if (visible && visible.height > 0) {
        scrollBoxIntoView(visible.top + distance, visible.height, visible.top > 0 ? 'start' : 'nearest');
      }
    });
  };
  const startOnceFitting = () => {
    if (frameFitsContent()) {
      start();
    }
  };
  window.addEventListener('resize', startOnceFitting);
  const timer = window.setTimeout(start, FRAME_RESIZE_TIMEOUT_MS);
}
