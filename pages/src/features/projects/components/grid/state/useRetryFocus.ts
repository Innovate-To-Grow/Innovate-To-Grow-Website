import {useEffect, useRef, type RefObject} from 'react';
import {focusWasDropped} from './useResultsFocus';

/**
 * Keeps keyboard focus in the grid through "Try again", whose button leaves with the error it answers. While the
 * rows load again, focus is on the loading line; then on the start of the results (the count line, or the empty
 * message when there are none), or back on Try again when the load fails again. Focus the visitor moved somewhere
 * else in the meantime is left there.
 */
export function useRetryFocus(
  loading: boolean,
  error: string | null | undefined,
  /** The count line, where the results start. */
  countRef: RefObject<HTMLElement | null>,
  /** The empty message, shown instead of the count when no rows came back. */
  emptyRef: RefObject<HTMLElement | null>,
) {
  const retrying = useRef(false);
  const loadingRef = useRef<HTMLParagraphElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!retrying.current) return;
    // Rows or another error: either way this retry is over.
    if (!loading) retrying.current = false;
    if (!focusWasDropped()) return;
    const resultsStart = countRef.current ?? emptyRef.current;
    const target = loading ? loadingRef.current : error ? retryRef.current : resultsStart;
    target?.focus();
  }, [countRef, emptyRef, error, loading]);

  const retry = (onRetry: () => void) => {
    retrying.current = true;
    onRetry();
  };

  return {loadingRef, retryRef, retry};
}
