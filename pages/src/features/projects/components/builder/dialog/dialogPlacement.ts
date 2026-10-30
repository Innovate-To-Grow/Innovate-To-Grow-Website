import {measureVisibleFramePart} from '../../shared/utils/partnerFrame';

/** Gap kept between the dialog and the edges of the part of the frame that is on screen. */
const VISIBLE_PART_MARGIN = 16;

/**
 * Opens a modal dialog where the visitor can see it.
 *
 * In the embed widget the frame is as tall as its content and the partner page scrolls instead, so a modal
 * centred in the frame's viewport can sit thousands of pixels from what is on screen (see partnerFrame.ts). There
 * the dialog is centred on the part of the frame that is on screen (and kept within it) before it opens. Opening
 * it there also keeps the focus it takes from scrolling the partner page. Outside a frame, or when the whole
 * frame is on screen, it opens at once where it is.
 *
 * Returns a cleanup that cancels a placement still waiting.
 */
export function openInVisiblePart(dialog: HTMLDialogElement, open: () => void): () => void {
  if (window.parent === window) {
    open();
    return () => {};
  }

  return measureVisibleFramePart((visible) => {
    if (visible && visible.height > 0 && visible.height < window.innerHeight - 1) {
      dialog.style.setProperty('--past-projects-dialog-center', `${visible.top + visible.height / 2}px`);
      dialog.style.setProperty('--past-projects-dialog-max-height', `${Math.max(visible.height - 2 * VISIBLE_PART_MARGIN, 0)}px`);
      dialog.classList.add('is-placed');
    }
    open();
  });
}
