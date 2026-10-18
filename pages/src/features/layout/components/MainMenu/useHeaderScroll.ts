import {useLayoutEffect, useState, type RefObject} from 'react';

/** Hide the phone site-name band once the page is scrolled past this offset (px)... */
export const BAND_HIDE_AFTER_PX = 40;
/** ...and show it again near the very top (hysteresis, px). */
export const BAND_SHOW_BELOW_PX = 4;

const readScrollY = () => (typeof window === 'undefined' ? 0 : window.scrollY || 0);

/**
 * Next hidden state of the phone site-name band.
 *
 * On phones the band is fixed under the blue bar while #menu-root keeps its
 * room (`reservedPx`, the band's height) in the page flow. That room sits
 * under the bar until `scrollY` reaches `reservedPx`; hiding the band any
 * earlier would leave it on screen as an empty strip. So the band hides only
 * once the room has scrolled away (and past BAND_HIDE_AFTER_PX), and comes
 * back as soon as the user scrolls up far enough for the room to show again
 * (or reaches BAND_SHOW_BELOW_PX). With no reserved room the plain 40/4px
 * hysteresis applies.
 */
export const nextBandHidden = (wasHidden: boolean, scrollY: number, reservedPx = 0): boolean => {
  const reserved = Number.isFinite(reservedPx) && reservedPx > 0 ? reservedPx : 0;
  return wasHidden
    ? scrollY >= Math.max(BAND_SHOW_BELOW_PX, reserved)
    : scrollY > Math.max(BAND_HIDE_AFTER_PX, reserved);
};

const readReservedPx = (headerRef?: RefObject<HTMLElement | null>): number => {
  const band = headerRef?.current?.querySelector<HTMLElement>('.site-header-band');
  return band ? band.getBoundingClientRect().height : 0;
};

/**
 * Whether the site-name band should be tucked away. The value is computed on
 * every viewport; only the phone header stylesheet acts on it (on desktop the
 * band simply scrolls away above the sticky menu row). `headerRef` points at
 * the header so the band's reserved height can be read.
 */
export const useHeaderBandHidden = (headerRef?: RefObject<HTMLElement | null>): boolean => {
  const [hidden, setHidden] = useState(() => nextBandHidden(false, readScrollY()));

  // Layout effect: the first check (which needs the mounted band) lands before paint.
  useLayoutEffect(() => {
    let frame = 0;
    let scheduled = false;
    const update = () => {
      scheduled = false;
      const scrollY = readScrollY();
      const reservedPx = readReservedPx(headerRef);
      setHidden((wasHidden) => nextBandHidden(wasHidden, scrollY, reservedPx));
    };
    // One state update per animation frame, however many scroll/resize events fire.
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', schedule, {passive: true});
    // The band's height changes with the breakpoint and when the web fonts load.
    window.addEventListener('resize', schedule);
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      if (scheduled) window.cancelAnimationFrame(frame);
    };
  }, [headerRef]);

  return hidden;
};

const HEADER_PARTS = [
  ['.site-header-bar', '--itg-header-bar-height'],
  ['.site-header-band', '--itg-header-band-height'],
  ['.site-header-menu', '--itg-header-menu-height'],
] as const;

/**
 * Publishes the rendered heights of the header parts as CSS custom properties
 * on <html>. The layout-menu sheet uses them for the sticky offset of
 * #menu-root (desktop: only the menu row stays), the phone header spacer, and
 * scroll-padding-top so focused/anchored content is never hidden under the
 * sticky header. The sheet carries fallbacks for the first paint.
 */
export const useHeaderMetrics = (headerRef: RefObject<HTMLElement | null>) => {
  useLayoutEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const root = document.documentElement;
    const parts = HEADER_PARTS.map(([selector, property]) => ({
      element: header.querySelector<HTMLElement>(selector),
      property,
    }));

    const apply = () => {
      for (const {element, property} of parts) {
        if (element) root.style.setProperty(property, `${element.getBoundingClientRect().height}px`);
      }
    };
    apply();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', apply);
      return () => window.removeEventListener('resize', apply);
    }
    const observer = new ResizeObserver(apply);
    for (const {element} of parts) {
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [headerRef]);
};
