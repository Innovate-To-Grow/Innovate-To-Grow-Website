import {useLayoutEffect, useState, type RefObject} from 'react';

/** Space the date takes beyond its own text: the utility's 12px gap and the divider's 12px padding (member.css). */
const DATE_GAP_PX = 12;
const DATE_DIVIDER_PX = 12;
/** Viewport width from which the date is assumed to fit before the row can be measured. */
const DATE_FIRST_GUESS_MIN_PX = 1200;

const px = (value: string) => Number.parseFloat(value) || 0;

/**
 * Whether the menu row's date has to be hidden, or null when the row has no
 * layout to measure (the phone header, jsdom) and the last answer stands.
 *
 * The date shows whenever it and the member link fit beside the menu with the
 * condensed logo's slot (--itg-menu-logo-slot) already reserved, so the answer
 * is the same at the top of the page and once the row is pinned: the date never
 * comes and goes on scroll. Short of room, the date goes first; the member
 * label shortens only when even that is not enough. A hidden date keeps its
 * width (member.css takes it out of the flow, unseen), so it can be measured.
 */
export const measureDateHidden = (header: HTMLElement): boolean | null => {
  const inner = header.querySelector<HTMLElement>('.site-header-menu-inner');
  const list = header.querySelector<HTMLElement>('.site-header-nav .menu-bar-list');
  const utility = header.querySelector<HTMLElement>('.site-header-utility');
  const date = header.querySelector<HTMLElement>('.site-header-date');
  // The loading skeleton is narrower than the real menu: deciding on it would show the date only to
  // take it away again when the items arrive.
  if (!inner || !list || !utility || !date || list.classList.contains('menu-bar-list--skeleton')) return null;

  const innerStyle = getComputedStyle(inner);
  const available = inner.clientWidth - px(innerStyle.paddingLeft) - px(innerStyle.paddingRight);
  if (available <= 0) return null;

  const menuWidth = Array.from(list.children).reduce((sum, item) => sum + item.getBoundingClientRect().width, 0);
  const logoSlot = px(getComputedStyle(header).getPropertyValue('--itg-menu-logo-slot'));
  const member = utility.querySelector<HTMLElement>('.site-header-member');
  let memberWidth = 0;
  if (member) {
    // Its natural width: without the divider padding it has only next to a shown date, and with
    // the part of the label that a squeezed row cuts off (up to the label's own 16rem cap, which
    // shortens a very long name whatever the room).
    const label = member.querySelector<HTMLElement>('.member-label');
    const labelCap = label ? px(getComputedStyle(label).maxWidth) || Number.POSITIVE_INFINITY : 0;
    memberWidth =
      member.getBoundingClientRect().width -
      px(getComputedStyle(member).paddingLeft) +
      (label ? Math.max(0, Math.min(label.scrollWidth, labelCap) - label.clientWidth) : 0);
  }
  const needed =
    logoSlot +
    menuWidth +
    px(innerStyle.columnGap) +
    date.getBoundingClientRect().width +
    DATE_GAP_PX +
    DATE_DIVIDER_PX +
    memberWidth +
    px(getComputedStyle(utility).marginRight);
  // 1px of slack against sub-pixel rounding.
  return needed + 1 > available;
};

/**
 * Calls `onChange` whenever the row may need measuring again: its width
 * changes, its content changes (menu items arriving, the member signing in),
 * the window resizes or the web fonts load. Returns the cleanup.
 */
const watchMenuRow = (inner: HTMLElement, onChange: () => void) => {
  const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onChange);
  resizeObserver?.observe(inner);
  const mutationObserver = typeof MutationObserver === 'undefined' ? null : new MutationObserver(onChange);
  mutationObserver?.observe(inner, {childList: true, subtree: true, characterData: true});
  window.addEventListener('resize', onChange);
  const fonts = document.fonts;
  fonts?.addEventListener?.('loadingdone', onChange);
  void fonts?.ready?.then(onChange);
  return () => {
    resizeObserver?.disconnect();
    mutationObserver?.disconnect();
    window.removeEventListener('resize', onChange);
    fonts?.removeEventListener?.('loadingdone', onChange);
  };
};

/**
 * Whether the header should carry .is-date-hidden. Measured before paint, then
 * again whenever the row changes (watchMenuRow). Those callbacks only schedule
 * the measurement for the next animation frame: the class it leads to changes
 * the row's layout (see the ResizeObserver rule in .claude/rules/frontend.md).
 */
export const useHeaderDateHidden = (headerRef: RefObject<HTMLElement | null>): boolean => {
  // Until the real menu can be measured, keep the old rule (the date only from 1200px up), so a
  // first measurement mostly confirms it instead of taking a shown date away.
  const [hidden, setHidden] = useState(() => typeof window !== 'undefined' && window.innerWidth < DATE_FIRST_GUESS_MIN_PX);

  useLayoutEffect(() => {
    const header = headerRef.current;
    const inner = header?.querySelector<HTMLElement>('.site-header-menu-inner');
    if (!header || !inner) return;

    const measure = () => {
      const next = measureDateHidden(header);
      if (next !== null) setHidden(next);
    };
    let frame = 0;
    let disposed = false;
    const schedule = () => {
      if (disposed || frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        measure();
      });
    };
    measure();
    const stopWatching = watchMenuRow(inner, schedule);

    return () => {
      disposed = true;
      stopWatching();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [headerRef]);

  return hidden;
};
