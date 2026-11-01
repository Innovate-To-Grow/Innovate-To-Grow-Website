import {useEffect, useState, type RefObject} from 'react';

/** Page controls the launcher must never sit on. */
const CONTROL_SELECTOR = [
  'a[href]',
  'button',
  'input:not([type="hidden"])',
  'select',
  'textarea',
  'summary',
  'label',
  '[role="button"]',
  '[role="link"]',
  '[role="checkbox"]',
  '[role="tab"]',
  '[role="switch"]',
  '[contenteditable="true"]',
].join(', ');

/** Hit-test points across the launcher's box (a 3 x 3 grid, 2px inside its edges). */
const GRID = [0, 0.5, 1];
const INSET = 2;

type HitTest = (x: number, y: number) => Element[];

const defaultHitTest: HitTest = (x, y) =>
  typeof document.elementsFromPoint === 'function' ? document.elementsFromPoint(x, y) : [];

/** Whether any page control (outside `ownRoot`, the widget itself) lies under `box`. */
export function coversPageControl(box: DOMRect, ownRoot: Element, hitTest: HitTest = defaultHitTest): boolean {
  const points = GRID.flatMap((fy) =>
    GRID.map((fx) => [box.left + INSET + fx * (box.width - 2 * INSET), box.top + INSET + fy * (box.height - 2 * INSET)]),
  );
  return points.some(([x, y]) =>
    hitTest(x, y).some((element) => !ownRoot.contains(element) && element.closest(CONTROL_SELECTOR) !== null),
  );
}

/**
 * The floating launcher sits in the viewport corner, which on most widths is over the page's own
 * right-hand controls (a row's Details button, the pager's Next). Whenever a control is under the
 * launcher's spot (`dockRef`, which never moves), it tucks into the page gutter (the caller styles it):
 * a tap there reaches the control, not the chat. Checked on scroll (also inside scrolling boxes),
 * resize, focus moves and page changes, at most once a frame. Never while the panel is open.
 */
export function useLauncherYield(
  dockRef: RefObject<HTMLElement | null>,
  ownRootRef: RefObject<HTMLElement | null>,
  enabled: boolean,
): boolean {
  const [tucked, setTucked] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let frame = 0;
    const check = () => {
      frame = 0;
      const dock = dockRef.current;
      const ownRoot = ownRootRef.current;
      if (dock && ownRoot) setTucked(coversPageControl(dock.getBoundingClientRect(), ownRoot));
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(check);
    };

    schedule();
    window.addEventListener('scroll', schedule, {passive: true, capture: true});
    window.addEventListener('resize', schedule);
    document.addEventListener('focusin', schedule);
    const mutations = new MutationObserver(schedule);
    mutations.observe(document.body, {childList: true, subtree: true});
    const resizes = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule);
    resizes?.observe(document.body);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule, {capture: true});
      window.removeEventListener('resize', schedule);
      document.removeEventListener('focusin', schedule);
      mutations.disconnect();
      resizes?.disconnect();
    };
  }, [dockRef, ownRootRef, enabled]);

  return enabled && tucked;
}
