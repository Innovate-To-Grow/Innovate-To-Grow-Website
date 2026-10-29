import {useLayoutEffect, useState, type RefObject} from 'react';
import {PHONE_MAX_WIDTH} from './parts/shared';

/** The condensed row lets go this far (px) before it would unpin, so scroll jitter at the threshold cannot flicker. */
export const CONDENSE_HYSTERESIS_PX = 8;

const readScrollY = () => (typeof window === 'undefined' ? 0 : window.scrollY || 0);

const isPhoneLayout = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia(`(max-width: ${PHONE_MAX_WIDTH}px)`).matches;

/**
 * Next condensed state of the desktop header.
 *
 * The blue bar and the site-name band scroll away with the page; once both
 * have gone (`pinAtPx`, their combined height) only the white menu row is
 * left, pinned at the top, and the header turns condensed: the round i2G logo
 * joins the front of the row. It leaves that state CONDENSE_HYSTERESIS_PX
 * before the row unpins. Without a measured height (phones, jsdom) it never
 * condenses.
 */
export const nextCondensed = (wasCondensed: boolean, scrollY: number, pinAtPx: number): boolean => {
  if (!Number.isFinite(pinAtPx) || pinAtPx <= 0) return false;
  return wasCondensed ? scrollY >= pinAtPx - CONDENSE_HYSTERESIS_PX : scrollY >= pinAtPx;
};

/** Combined height of the parts above the menu row; 0 on phones, whose one bar never changes. */
const readPinAtPx = (headerRef: RefObject<HTMLElement | null>): number => {
  const header = headerRef.current;
  if (!header || isPhoneLayout()) return 0;
  const height = (selector: string) => header.querySelector<HTMLElement>(selector)?.getBoundingClientRect().height ?? 0;
  return height('.site-header-bar') + height('.site-header-band');
};

/**
 * Whether the desktop header is condensed (only the pinned menu row with the
 * logo shows), and whether its transitions may run yet. Motion is switched on
 * only after the first state is in place, so a reload that restores a
 * scrolled position does not play the condense animation.
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
    // The bar and band heights change with the breakpoint and when the web fonts load.
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
  ['.site-header-band', '--itg-header-band-height'],
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
