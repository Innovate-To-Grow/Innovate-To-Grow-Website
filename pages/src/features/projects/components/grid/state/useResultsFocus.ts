import {useEffect, useRef, type FocusEvent, type RefObject} from 'react';

/** The focused element left the page, which drops focus to <body>. */
export const focusWasDropped = () => !document.activeElement || document.activeElement === document.body;

/**
 * Focuses the start of the results (the count line), so a new page or answer is read from its first row, not its
 * last: the control the visitor was on, a pager step button or a row, may have just been disabled or taken away,
 * which dropped focus to the page. Scrolls it under the sticky header (the page's scroll-padding-top) only when it is
 * out of view.
 */
export const showResultsStart = (resultsStart: HTMLElement) => {
  resultsStart.focus({preventScroll: true});
  const headerSpace = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
  const {top} = resultsStart.getBoundingClientRect();
  if (top < headerSpace || top > window.innerHeight) resultsStart.scrollIntoView({block: 'start'});
};

// The grid's own controls that can leave, or turn disabled, while the visitor is on them: the no-results message
// with its Clear button (and any action beside it), and the pager.
const RESULTS_CONTROLS = '.project-grid-no-results, .project-grid-pagination';
// A row's controls: its link, checkbox, Details and Remove, and the links in its opened details. They leave the page
// when the server's answer sorts other rows in above them. A row the visitor took away (Remove from Table) is left to
// the table's owner, which knows where its focus belongs.
const ROW_CONTROLS = '.project-grid-row, .project-grid-detail-row, .project-grid-mobile-card';

/** The control left the page, or turned disabled, with focus on it. */
const tookFocusAway = (control: Element) => {
  const gone = !control.isConnected || control.matches(':disabled');
  // A disabled button drops focus to the page in some browsers and keeps it, answering no keys, in others.
  return gone && (focusWasDropped() || document.activeElement === control);
};

/**
 * Keeps keyboard focus in the grid when its results change without the visitor asking. The server's answer to a
 * search can replace the no-results message, Clear button included, with rows, send the table back to its first
 * page, which disables Previous, or sort rows in above the one the visitor is on, which moves it to a later page;
 * each dropped focus to the page. Focus that fell from one of those controls goes to the start of the results: the
 * count line, or the empty message. Focus the visitor moved elsewhere stays.
 *
 * `addedRowsKey` is the server search's key of the answer that last added rows (ProjectGridServerSearch).
 * Returns the focus handlers for the grid's outer element.
 */
export function useResultsFocus(
  countRef: RefObject<HTMLElement | null>,
  emptyRef: RefObject<HTMLElement | null>,
  addedRowsKey: string | null,
) {
  const lastFocused = useRef<Element | null>(null);
  const answerSeen = useRef(addedRowsKey);

  // Checked after every render: the results change with the rows, page and search the grid is given.
  useEffect(() => {
    // An answer added rows in this render, so the rows on the page may be others than before.
    const answerMovedRows = addedRowsKey !== null && addedRowsKey !== answerSeen.current;
    answerSeen.current = addedRowsKey;
    const control = lastFocused.current;
    // A removed element keeps the subtree it left with, so this still finds the no-results message, pager or row.
    const watched = answerMovedRows ? `${RESULTS_CONTROLS}, ${ROW_CONTROLS}` : RESULTS_CONTROLS;
    if (!control?.closest(watched) || !tookFocusAway(control)) return;
    lastFocused.current = null;
    const resultsStart = countRef.current ?? emptyRef.current;
    if (resultsStart) showResultsStart(resultsStart);
  });

  return {
    onFocus: (event: FocusEvent<HTMLElement>) => {
      lastFocused.current = event.target;
    },
    onBlur: (event: FocusEvent<HTMLElement>) => {
      // Focus left a control that is still there and usable: the visitor moved it, and where it went is theirs.
      // (A control that leaves the page, or turns disabled, under the visitor fails one of these.)
      const control = event.target;
      if (control === lastFocused.current && control.isConnected && !control.matches(':disabled')) {
        lastFocused.current = null;
      }
    },
  };
}
