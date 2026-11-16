import {useLayoutEffect, useState, type RefObject} from 'react';

/** The condensed state lets go this far (px) before its threshold, so scroll jitter there cannot flicker. */
export const CONDENSE_HYSTERESIS_PX = 8;

const readScrollY = () => (typeof window === 'undefined' ? 0 : window.scrollY || 0);

/**
 * Next condensed state of the header: condensed once the page has scrolled by
 * the blue bar's height (`pinAtPx`), and back CONDENSE_HYSTERESIS_PX before
 * that. Without a measured height (jsdom) it never condenses.
 *
 * Desktop: the bar has scrolled away, so only the white menu row is left,
 * pinned at the top, and the round i2G logo joins its front.
 * Phone: the fixed bar stays, and its UC Merced wordmark gives way to the
 * round i2G logo.
 */
export const nextCondensed = (wasCondensed: boolean, scrollY: number, pinAtPx: number): boolean => {
  if (!Number.isFinite(pinAtPx) || pinAtPx <= 0) return false;
  return wasCondensed ? scrollY >= pinAtPx - CONDENSE_HYSTERESIS_PX : scrollY >= pinAtPx;
};

/** Height of the blue bar: what has to scroll by before the header condenses. */
const readPinAtPx = (headerRef: RefObject<HTMLElement | null>): number =>
  headerRef.current?.querySelector<HTMLElement>('.site-header-bar')?.getBoundingClientRect().height ?? 0;

/**
 * Whether the header is condensed (nextCondensed), and whether its transitions
 * may run yet. Motion is switched on only after the first state is in place,
 * so a reload that restores a scrolled position does not play the animation.
 */
export const useHeaderCondensed = (headerRef: RefObject<HTMLElement | null>) => {
  const [isCondensed, setIsCondensed] = useState(false);
  const [hasMotion, setHasMotion] = useState(false);

  // Layout effect: the first check (which needs the mounted header) lands before paint.
  useLayoutEffect(() => {
    let frame = 0;
    let scheduled = false;
    const update = () => {
      scheduled = false;
      const scrollY = readScrollY();
      const pinAtPx = readPinAtPx(headerRef);
      setIsCondensed((wasCondensed) => nextCondensed(wasCondensed, scrollY, pinAtPx));
    };
    // One state update per animation frame, however many scroll/resize events fire.
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      frame = window.requestAnimationFrame(update);
    };
    update();
    let motionFrame = 0;
    motionFrame = window.requestAnimationFrame(() => {
      motionFrame = window.requestAnimationFrame(() => setHasMotion(true));
    });
    window.addEventListener('scroll', schedule, {passive: true});
    // The bar's height changes with the breakpoint.
    window.addEventListener('resize', schedule);
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      if (scheduled) window.cancelAnimationFrame(frame);
      window.cancelAnimationFrame(motionFrame);
    };
  }, [headerRef]);

  return {isCondensed, hasMotion};
};

const HEADER_PARTS = [
  ['.site-header-bar', '--itg-header-bar-height'],
  ['.site-header-menu', '--itg-header-menu-height'],
] as const;

/**
 * Publishes the rendered heights of the header parts as CSS custom properties
 * on <html>. MainMenu.css uses them for the sticky offset of
 * #menu-root (desktop: only the menu row stays), the phone header spacer, and
 * scroll-padding-top so focused/anchored content is never hidden under the
 * sticky header. The sheet carries fallbacks for the first paint.
 *
 * The first measurement is written before paint. Later ones, reported by a
 * ResizeObserver, are written on the next animation frame: the sheet feeds
 * these properties back into the header's own box (#menu-root's height and
 * sticky offset), so writing them inside the observer callback resizes an
 * observed part in the same frame, which WebKit reports as the page error
 * "ResizeObserver loop completed with undelivered notifications". Unchanged
 * heights are not rewritten.
 */
export const useHeaderMetrics = (headerRef: RefObject<HTMLElement | null>) => {
  useLayoutEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const root = document.documentElement;
    const parts = HEADER_PARTS.map(([selector, property]) => ({
      element: header.querySelector<HTMLElement>(selector),
      property,
      published: '',
    }));

    const apply = () => {
      for (const part of parts) {
        if (!part.element) continue;
        const height = `${part.element.getBoundingClientRect().height}px`;
        if (height === part.published) continue;
        part.published = height;
        root.style.setProperty(part.property, height);
      }
    };
    apply();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', apply);
      return () => window.removeEventListener('resize', apply);
    }
    let frame = 0;
    const observer = new ResizeObserver(() => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        apply();
      });
    });
    for (const {element} of parts) {
      if (element) observer.observe(element);
    }
    return () => {
      observer.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [headerRef]);
};
