import {useEffect, useRef, useState} from 'react';

interface RetryInPlaceOptions {
  /** A load is running. */
  loading: boolean;
  /** The last load failed: its failure, with a Try Again button, is shown. */
  failed: boolean;
  onRetry: () => void;
  /** What takes focus when a retry brings what failed to load, and the failure goes with the focused button. */
  focusTarget: () => HTMLElement | null;
}

/**
 * "Try Again" after a failed load. Loading again clears the failure, and the Try Again button, which has keyboard
 * focus, went with it: focus dropped to the page. So the failure stays while the retry runs (`retrying`: its button
 * marked busy, its text saying what loads) and goes only once the retry has brought what failed. Focus, left on the
 * page's body when it goes, then moves to `focusTarget`; a retry that fails again leaves it on Try Again.
 *
 * `showFailure` says when to show the failure; `retry` is Try Again's handler.
 */
export function useRetryInPlace({loading, failed, onRetry, focusTarget}: RetryInPlaceOptions) {
  const [retrying, setRetrying] = useState(false);
  const movesFocus = useRef(false);
  // The retry has ended, either way: a failed one shows its failure again through `failed`.
  if (retrying && !loading) {
    setRetrying(false);
  }
  const showFailure = failed || retrying;

  useEffect(() => {
    if (showFailure || !movesFocus.current) {
      return;
    }
    movesFocus.current = false;
    if (!document.activeElement || document.activeElement === document.body) {
      focusTarget()?.focus();
    }
  }, [showFailure, focusTarget]);

  const retry = () => {
    if (retrying) {
      return;
    }
    movesFocus.current = true;
    setRetrying(true);
    onRetry();
  };

  return {retrying, showFailure, retry};
}
