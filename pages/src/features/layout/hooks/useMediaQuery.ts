import {useCallback, useSyncExternalStore} from 'react';

const canMatchMedia = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function';

/** Live result of a CSS media query; false where matchMedia is unavailable (tests, SSR). */
export const useMediaQuery = (query: string): boolean => {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!canMatchMedia()) return () => {};
      const list = window.matchMedia(query);
      if (typeof list.addEventListener === 'function') {
        list.addEventListener('change', onChange);
        return () => list.removeEventListener('change', onChange);
      }
      list.addListener(onChange);
      return () => list.removeListener(onChange);
    },
    [query],
  );
  const getSnapshot = useCallback(() => (canMatchMedia() ? window.matchMedia(query).matches : false), [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
};
