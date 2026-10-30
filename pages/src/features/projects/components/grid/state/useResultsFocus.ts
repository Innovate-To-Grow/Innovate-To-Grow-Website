import {useEffect, useRef, type FocusEvent, type RefObject} from 'react';

/** The focused element left the page, which drops focus to <body>. */
export const focusWasDropped = () => !document.activeElement || document.activeElement === document.body;

// The grid's own controls that can leave, or turn disabled, while the visitor is on them: the no-results message
// with its Clear button (and any action beside it), and the pager.
const RESULTS_CONTROLS = '.project-grid-no-results, .project-grid-pagination';

/**
 * Keeps keyboard focus in the grid when its results change without the visitor asking. The server's answer to a
 * search can replace the no-results message, Clear button included, with rows, or send the table back to its first
 * page, which disables Previous; either dropped focus to the page. Focus that fell from one of those controls goes
 * to the start of the results: the count line, or the empty message. Focus the visitor moved elsewhere stays.
 *
 * Returns the focus handler for the grid's outer element.
 */
export function useResultsFocus(
  countRef: RefObject<HTMLElement | null>,
  emptyRef: RefObject<HTMLElement | null>,
) {
  const lastFocused = useRef<Element | null>(null);

  // Checked after every render: the results change with the rows, page and search the grid is given.
  useEffect(() => {
    const control = lastFocused.current;
    // A removed element keeps the subtree it left with, so this still finds the no-results message or the pager.
    if (!control?.closest(RESULTS_CONTROLS)) return;
    const gone = !control.isConnected || control.matches(':disabled');
    // A disabled button drops focus to the page in some browsers and keeps it, answering no keys, in others.
    const stranded = focusWasDropped() || document.activeElement === control;
    if (!gone || !stranded) return;
    lastFocused.current = null;
    (countRef.current ?? emptyRef.current)?.focus();
  });

  return (event: FocusEvent<HTMLElement>) => {
    lastFocused.current = event.target;
  };
}
