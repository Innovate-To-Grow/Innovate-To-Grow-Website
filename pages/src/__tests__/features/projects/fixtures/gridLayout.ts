import {vi} from 'vitest';

/** The query the project grid renders its phone list for (ProjectGridTable). */
const PHONE_LAYOUT_QUERY = '(max-width: 768px)';

/**
 * Stubs `window.matchMedia` so the project grid renders its desktop table or its phone list (jsdom has no
 * matchMedia, which renders the table). `setPhone` crosses the breakpoint like a resize. Undo it with
 * `vi.unstubAllGlobals()`.
 */
export function stubGridLayout(initial: 'desktop' | 'phone' = 'desktop') {
  let isPhone = initial === 'phone';
  const listeners = new Set<() => void>();
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return isPhone && query === PHONE_LAYOUT_QUERY;
    },
    media: query,
    addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
  }));
  return {
    setPhone(next: boolean) {
      isPhone = next;
      listeners.forEach((listener) => listener());
    },
  };
}
