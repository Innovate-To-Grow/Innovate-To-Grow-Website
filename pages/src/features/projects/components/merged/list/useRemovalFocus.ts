import {useCallback, useEffect, useRef} from 'react';
import type {ProjectGridItem} from '../../grid/contracts/projectGrid';

const REMOVE_BUTTON = '.project-grid-delete-button';

interface PendingRemoval {
  rowKey: string;
  /** The rows the pressed button sat among: the table body, or the phone list. */
  list: Element;
  index: number;
}

/**
 * A row's Remove takes the row away with the button that was pressed, which dropped keyboard focus to the page.
 * Call the returned function as a Remove is pressed: once the row has gone, focus moves to the Remove of the row
 * that took its place, else of the row above, else (no rows left on the page) to the list's heading.
 */
export function useRemovalFocus(rows: ProjectGridItem[], headingId: string) {
  const pending = useRef<PendingRemoval | null>(null);

  const rememberRemoval = useCallback((row: ProjectGridItem) => {
    const pressed = document.activeElement;
    const list = pressed?.matches(REMOVE_BUTTON) ? pressed.closest('tbody, ol') : null;
    pending.current =
      pressed && list ? {rowKey: row.__key, list, index: [...list.querySelectorAll(REMOVE_BUTTON)].indexOf(pressed)} : null;
  }, []);

  useEffect(() => {
    const removal = pending.current;
    // A shared page removes once its save lands; until the row is gone (or if the save fails) nothing moves.
    if (!removal || rows.some((row) => row.__key === removal.rowKey)) {
      return;
    }
    pending.current = null;
    const buttons = removal.list.isConnected ? [...removal.list.querySelectorAll<HTMLElement>(REMOVE_BUTTON)] : [];
    const target = buttons[Math.min(removal.index, buttons.length - 1)] ?? document.getElementById(headingId);
    target?.focus();
  }, [rows, headingId]);

  return rememberRemoval;
}
