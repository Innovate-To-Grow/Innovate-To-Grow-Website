/** Gap kept between the dialog and the edges of the part of the frame that is on screen. */
const VISIBLE_PART_MARGIN = 16;

// How long to wait for the observer before opening the dialog where it is anyway.
const PLACEMENT_TIMEOUT_MS = 300;

/**
 * Opens a modal dialog where the visitor can see it.
 *
 * In the embed widget the frame is as tall as its content and the partner page scrolls instead, so the frame's
 * viewport is the whole widget: a modal centred in it can sit thousands of pixels from what is on screen, and
 * the frame cannot read the partner page's scroll position. An IntersectionObserver can still say which part
 * of the frame is on screen, so there the dialog is centred on that part (and kept within it) before it opens.
 * Opening it there also keeps the focus it takes from scrolling the partner page. Outside a frame, or when the
 * whole frame is on screen, it opens at once where it is.
 *
 * Returns a cleanup that cancels a placement still waiting.
 */
export function openInVisiblePart(dialog: HTMLDialogElement, open: () => void): () => void {
  if (window.parent === window || typeof IntersectionObserver === 'undefined') {
    open();
    return () => {};
  }

  let settled = false;
  const settle = (visible?: DOMRectReadOnly) => {
    if (settled) {
      return;
    }
    settled = true;
    observer.disconnect();
    window.clearTimeout(timer);
    if (visible && visible.height > 0 && visible.height < window.innerHeight - 1) {
      dialog.style.setProperty('--past-projects-dialog-center', `${visible.top + visible.height / 2}px`);
      dialog.style.setProperty('--past-projects-dialog-max-height', `${Math.max(visible.height - 2 * VISIBLE_PART_MARGIN, 0)}px`);
      dialog.classList.add('is-placed');
    }
    open();
  };
  const observer = new IntersectionObserver(([entry]) => settle(entry?.intersectionRect));
  const timer = window.setTimeout(() => settle(), PLACEMENT_TIMEOUT_MS);
  observer.observe(document.documentElement);

  return () => {
    settled = true;
    observer.disconnect();
    window.clearTimeout(timer);
  };
}
