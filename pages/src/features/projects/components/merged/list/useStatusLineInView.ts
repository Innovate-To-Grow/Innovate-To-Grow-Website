import {useCallback, useEffect, useRef, type PointerEvent} from 'react';

/** Room kept between the line, or what was acted on, and the screen's edges. */
const EDGE_MARGIN = 16;
/** How long after a press the press still explains a message (Safari does not focus a button it clicks). */
const PRESS_EXPLAINS_MS = 1000;

interface Press {
  y: number;
  time: number;
}

/** Where on screen the visitor acted in the card: the focused control, else a press just now; null when neither. */
const actedOnTop = (card: HTMLElement, press: Press | null) => {
  const active = document.activeElement;
  if (active && active !== document.body && card.contains(active)) {
    return active.getBoundingClientRect().top;
  }
  return press && performance.now() - press.time < PRESS_EXPLAINS_MS ? press.y : null;
};

/**
 * Scrolls the card's status line (under its table) into view when it reports something done in the card. A row's
 * Remove sits up to a page of rows above the line, so with the card's top on screen its message could land below
 * the screen's bottom edge, where only screen readers (it is role=status) noticed it. The page moves only as far as
 * the line needs, and only when what the visitor acted on (the focused control, else where they pressed) stays on
 * screen; a message the card did not cause (another tab's change, a save from a search table) moves nothing.
 * `statusReports` counts the reports, so one that repeats the line's text is shown again too.
 *
 * Returns the refs for the card and its line, and the card's pointer-down handler.
 */
export function useStatusLineInView(statusMessage: string, statusReports: number) {
  const cardRef = useRef<HTMLElement>(null);
  const lineRef = useRef<HTMLParagraphElement>(null);
  const lastPress = useRef<Press | null>(null);

  const onPointerDown = useCallback((event: PointerEvent) => {
    lastPress.current = {y: event.clientY, time: performance.now()};
  }, []);

  useEffect(() => {
    const card = cardRef.current;
    const line = lineRef.current;
    if (!statusMessage || !card || !line) {
      return;
    }
    const overflow = line.getBoundingClientRect().bottom + EDGE_MARGIN - window.innerHeight;
    if (overflow <= 0) {
      return;
    }
    const top = actedOnTop(card, lastPress.current);
    if (top !== null && top - overflow >= EDGE_MARGIN) {
      window.scrollBy(0, overflow);
    }
  }, [statusMessage, statusReports]);

  return {cardRef, lineRef, onPointerDown};
}
