import {measureVisibleFramePart, scrollFrameBoxIntoView} from '../../shared/utils/partnerFrame';

/** Gap kept between the dialog and the edges of the part of the frame that is on screen. */
const VISIBLE_PART_MARGIN = 16;

/** What opening a dialog does, in two steps, so it can be placed once shown (and sized) but before it takes focus. */
export interface DialogOpening {
  show: () => void;
  focus: () => void;
}

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, max));

/**
 * Centres the shown dialog on the part of the frame that is on screen. A dialog too tall for that part keeps its
 * height (squeezed into it, it scrolled its own question out of sight) and moves only as far as the frame's edges
 * make it; the box it then takes, to bring on screen, is returned. Null when it fits.
 */
function centreOnVisiblePart(dialog: HTMLDialogElement, visible: DOMRectReadOnly, show: () => void) {
  const centre = visible.top + visible.height / 2;
  dialog.style.setProperty('--past-projects-dialog-center', `${centre}px`);
  dialog.classList.add('is-placed');
  show();
  const height = dialog.offsetHeight;
  if (height <= visible.height - 2 * VISIBLE_PART_MARGIN) {
    return null;
  }
  const halfHeight = height / 2 + VISIBLE_PART_MARGIN;
  const keptCentre = clamp(centre, halfHeight, window.innerHeight - halfHeight);
  dialog.style.setProperty('--past-projects-dialog-center', `${keptCentre}px`);
  return {top: keptCentre - halfHeight, height: 2 * halfHeight};
}

/**
 * Opens a modal dialog where the visitor can see it.
 *
 * In the embed widget the frame is as tall as its content and the partner page scrolls instead, so a modal
 * centred in the frame's viewport can sit thousands of pixels from what is on screen (see partnerFrame.ts). There
 * the dialog is centred on the part of the frame that is on screen before it takes focus, which also keeps the
 * focus from scrolling the partner page to it. When that part is too short for the dialog, the partner page is then
 * scrolled to show all of it. Outside a frame, or when the whole frame is on screen, it opens at once where it is.
 *
 * Returns a cleanup that cancels a placement still waiting.
 */
export function openInVisiblePart(dialog: HTMLDialogElement, {show, focus}: DialogOpening): () => void {
  if (window.parent === window) {
    show();
    focus();
    return () => {};
  }

  return measureVisibleFramePart((visible) => {
    let overflow = null;
    if (visible && visible.height > 0 && visible.height < window.innerHeight - 1) {
      overflow = centreOnVisiblePart(dialog, visible, show);
    } else {
      show();
    }
    focus();
    if (overflow) {
      scrollFrameBoxIntoView(overflow.top, overflow.height, 'nearest');
    }
  });
}
