import {act, cleanup, renderHook} from '@testing-library/react';
import type {ReactNode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
  LayoutContext,
  type LayoutContextValue,
} from '@/features/layout/components/LayoutProvider/context';
import {useMainMenuState} from '@/features/layout/components/MainMenu/useMainMenuState';

const useAuth = vi.hoisted(() => vi.fn());

vi.mock('@/features/auth', () => ({
  useAuth,
}));

let layoutValue: LayoutContextValue;

const wrapper = ({children}: {children: ReactNode}) => (
  <LayoutContext.Provider value={layoutValue}>{children}</LayoutContext.Provider>
);

describe('useMainMenuState', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    layoutValue = {state: 'loading', menus: [], footer: null, error: null};
    useAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('toggles the mobile menu on the toggle-menu window event', () => {
    const {result} = renderHook(() => useMainMenuState(), {wrapper});
    expect(result.current.isMobileOpen).toBe(false);

    act(() => window.dispatchEvent(new Event('toggle-menu')));
    expect(result.current.isMobileOpen).toBe(true);

    act(() => window.dispatchEvent(new Event('toggle-menu')));
    expect(result.current.isMobileOpen).toBe(false);
  });

  it('closes the mobile menu when resized above the breakpoint', () => {
    const {result} = renderHook(() => useMainMenuState(), {wrapper});
    act(() => result.current.setIsMobileOpen(true));
    expect(result.current.isMobileOpen).toBe(true);

    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1200);
    act(() => window.dispatchEvent(new Event('resize')));
    expect(result.current.isMobileOpen).toBe(false);
  });

  it('keeps the mobile menu open at or below the breakpoint', () => {
    const {result} = renderHook(() => useMainMenuState(), {wrapper});
    act(() => result.current.setIsMobileOpen(true));

    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(992);
    act(() => window.dispatchEvent(new Event('resize')));
    expect(result.current.isMobileOpen).toBe(true);
  });

  it('locks body scrolling while the mobile menu is open', () => {
    const {result} = renderHook(() => useMainMenuState(), {wrapper});
    expect(document.body.style.overflow).toBe('');

    act(() => result.current.setIsMobileOpen(true));
    expect(document.body.style.overflow).toBe('hidden');

    act(() => result.current.setIsMobileOpen(false));
    expect(document.body.style.overflow).toBe('');
  });

  it('marks the root element while the mobile menu is open', () => {
    const {result, unmount} = renderHook(() => useMainMenuState(), {wrapper});
    expect(document.documentElement).not.toHaveClass('is-mobile-menu-open');

    act(() => result.current.setIsMobileOpen(true));
    expect(document.documentElement).toHaveClass('is-mobile-menu-open');

    act(() => result.current.setIsMobileOpen(false));
    expect(document.documentElement).not.toHaveClass('is-mobile-menu-open');

    act(() => result.current.setIsMobileOpen(true));
    unmount();
    expect(document.documentElement).not.toHaveClass('is-mobile-menu-open');
  });

  describe('page roots behind the open phone menu', () => {
    const roots: HTMLElement[] = [];

    /** One of the page's roots from pages/index.html, optionally inert already. */
    const addRoot = (id: string, {inert = false} = {}) => {
      const root = document.createElement(id === 'main' ? 'main' : 'div');
      root.id = id;
      if (inert) root.setAttribute('inert', '');
      document.body.appendChild(root);
      roots.push(root);
      return root;
    };

    const inertIds = () => roots.filter((root) => root.hasAttribute('inert')).map((root) => root.id);

    afterEach(() => {
      for (const root of roots.splice(0)) root.remove();
    });

    it('makes #main, #footer-root and #chatbot-root inert while the menu is open', () => {
      addRoot('main');
      addRoot('footer-root');
      addRoot('chatbot-root');
      // The header's own root is never covered.
      const menuRoot = addRoot('menu-root');
      const {result} = renderHook(() => useMainMenuState(), {wrapper});
      expect(inertIds()).toEqual([]);

      act(() => result.current.setIsMobileOpen(true));
      expect(inertIds()).toEqual(['main', 'footer-root', 'chatbot-root']);
      expect(menuRoot).not.toHaveAttribute('inert');

      act(() => result.current.setIsMobileOpen(false));
      expect(inertIds()).toEqual([]);
    });

    it('leaves a root that was inert already as it was on close', () => {
      addRoot('main');
      addRoot('footer-root', {inert: true});
      addRoot('chatbot-root');
      const {result} = renderHook(() => useMainMenuState(), {wrapper});

      act(() => result.current.setIsMobileOpen(true));
      expect(inertIds()).toEqual(['main', 'footer-root', 'chatbot-root']);

      act(() => result.current.setIsMobileOpen(false));
      expect(inertIds()).toEqual(['footer-root']);
    });

    it('copes with roots the page does not have', () => {
      const {result, unmount} = renderHook(() => useMainMenuState(), {wrapper});
      act(() => result.current.setIsMobileOpen(true));
      act(() => result.current.setIsMobileOpen(false));

      addRoot('main');
      act(() => result.current.setIsMobileOpen(true));
      expect(inertIds()).toEqual(['main']);
      unmount();
      expect(inertIds()).toEqual([]);
    });

    it('releases the roots it made inert when it unmounts with the menu open', () => {
      addRoot('main');
      addRoot('footer-root');
      addRoot('chatbot-root', {inert: true});
      const {result, unmount} = renderHook(() => useMainMenuState(), {wrapper});
      act(() => result.current.setIsMobileOpen(true));
      expect(inertIds()).toEqual(['main', 'footer-root', 'chatbot-root']);

      unmount();
      expect(inertIds()).toEqual(['chatbot-root']);
      expect(document.body.style.overflow).toBe('');
    });
  });
});
