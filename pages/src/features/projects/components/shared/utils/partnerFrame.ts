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

/*
 * WebKit does not let scrollIntoView in a frame from another site scroll the page around it, so in Safari the
 * widget could not scroll the partner page at all. A partner page whose snippet can scroll the page for the widget
 * says so: the widget posts {type: SCROLL_HELLO, slug} to it, and the snippet answers {type: SCROLL_READY}. From
 * then on the widget asks it, with {type: SCROLL_INTO_VIEW, slug, top, height, block, smooth}, to scroll the page as
 * scrollIntoView({block}) would bring the frame's box from `top` (frame client coordinates, the same as the frame's
 * page ones: the frame does not scroll) `height` pixels tall on screen. Snippets that cannot never answer, and the
 * widget keeps using scrollIntoView, which Chromium and Firefox carry over to the partner page.
 */
const SCROLL_HELLO = 'i2g-embed-scroll-hello';
const SCROLL_READY = 'i2g-embed-scroll-ready';
const SCROLL_INTO_VIEW = 'i2g-embed-scroll-into-view';

let partnerPageScrolls = false;

/** The widget's slug, from its address (`/_embed/<slug>`), as its resize messages carry it; null outside one. */
const widgetSlug = () => {
  const match = /^\/_embed\/([^/]+)/.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
};

/**
 * Asks the partner page around the widget whether its snippet scrolls the page when asked (see above), and listens
 * for the answer. Returns a cleanup that stops listening and forgets the answer. A no-op outside the widget.
 */
export function askPartnerPageToScroll(): () => void {
  const slug = widgetSlug();
  if (window.parent === window || slug === null) {
    return () => {};
  }
  const handleMessage = (event: MessageEvent) => {
    if (event.source === window.parent && (event.data as {type?: unknown} | null)?.type === SCROLL_READY) {
      partnerPageScrolls = true;
    }
  };
  window.addEventListener('message', handleMessage);
  // Any partner page may host the widget, so its origin is not known; the message carries nothing private.
  window.parent.postMessage({type: SCROLL_HELLO, slug}, '*');
  return () => {
    window.removeEventListener('message', handleMessage);
    partnerPageScrolls = false;
  };
}

/**
 * Scrolls a box (client coordinates) into view, which scrolls the frame's ancestors as needed: through the partner
 * page's snippet when it said it can, else with a hidden box of the same size. The box ends at the frame's bottom at
 * the latest: one that reached past it would let the frame's own document scroll.
 */
export function scrollFrameBoxIntoView(top: number, height: number, block: 'start' | 'nearest', smooth = false) {
  const boxTop = Math.min(top, window.innerHeight - 1);
  const boxHeight = Math.max(Math.min(height, window.innerHeight - boxTop), 1);
  if (partnerPageScrolls) {
    window.parent.postMessage(
      {type: SCROLL_INTO_VIEW, slug: widgetSlug(), top: boxTop, height: boxHeight, block, smooth},
      '*',
    );
    return;
  }
  const probe = document.createElement('div');
  probe.style.cssText = 'position:absolute;left:0;top:0;width:1px;visibility:hidden;pointer-events:none';
  probe.style.height = `${boxHeight}px`;
  document.body.append(probe);
  // Its containing block may not start at the top of the page.
  probe.style.top = `${boxTop - probe.getBoundingClientRect().top}px`;
  probe.scrollIntoView({block, behavior: smooth ? 'smooth' : 'auto'});
  probe.remove();
}

/**
 * Scrolls the partner page by `distance`, as `window.scrollBy` scrolls a page of its own: a box over the visible
 * part, moved by `distance`, is scrolled into view, lined up with the screen's top edge when the frame runs past
 * it, else just far enough to be all on screen. That waits until the partner page has resized the frame to its
 * new content, which can take more than one step (until then the frame's own document would scroll instead).
 * In WebKit only a snippet that scrolls the page when asked (see scrollFrameBoxIntoView) moves it.
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
        scrollFrameBoxIntoView(visible.top + distance, visible.height, visible.top > 0 ? 'start' : 'nearest');
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
