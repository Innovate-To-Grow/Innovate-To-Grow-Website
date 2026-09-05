import {act, cleanup, renderHook} from '@testing-library/react';
import type {ReactNode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {Menu, MenuItem} from '@/features/layout/api';
import {
  LayoutContext,
  type LayoutContextValue,
} from '@/features/layout/components/LayoutProvider/context';
import {formatCurrentMenuDate} from '@/features/layout/components/MainMenu/parts/shared';
import {useMainMenuState} from '@/features/layout/components/MainMenu/useMainMenuState';

const useAuth = vi.hoisted(() => vi.fn());

vi.mock('@/features/auth', () => ({
  useAuth,
}));

const item: MenuItem = {
  title: 'Home',
  url: '/',
  type: 'home',
  open_in_new_tab: false,
  children: [],
};

const makeMenu = (name: string, items: MenuItem[] = []): Menu => ({
  id: `menu-${name}`,
  name,
  display_name: name,
  description: null,
  items,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

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

  it('returns the current date, menu items, and auth state', () => {
    const menu = makeMenu('main', [item]);
    layoutValue = {state: 'ready', menus: [menu], footer: null, error: null};
    const {result} = renderHook(() => useMainMenuState(), {wrapper});

    expect(result.current.currentDate).toBe(formatCurrentMenuDate());
    expect(result.current.menuItems).toEqual([item]);
    expect(result.current.state).toBe('ready');
    expect(result.current.isAuthenticated).toBe(false);
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

  it('refreshes the member profile once when authenticated without a profile image', () => {
    const refreshProfile = vi.fn();
    useAuth.mockReturnValue({
      user: {member_uuid: 'u', email: 'a@b.c'},
      isAuthenticated: true,
      logout: vi.fn(),
      refreshProfile,
    });

    const {result} = renderHook(() => useMainMenuState(), {wrapper});
    expect(result.current.isAuthenticated).toBe(true);
    expect(refreshProfile).toHaveBeenCalledTimes(1);
  });

  it('does not refresh when the profile image is already present', () => {
    const refreshProfile = vi.fn();
    useAuth.mockReturnValue({
      user: {member_uuid: 'u', email: 'a@b.c', profile_image: '/img.png'},
      isAuthenticated: true,
      logout: vi.fn(),
      refreshProfile,
    });

    renderHook(() => useMainMenuState(), {wrapper});
    expect(refreshProfile).not.toHaveBeenCalled();
  });

  it('re-syncs the profile after signing out and back in', () => {
    const refreshProfile = vi.fn();
    const authed = {
      user: {member_uuid: 'u', email: 'a@b.c'},
      isAuthenticated: true,
      logout: vi.fn(),
      refreshProfile,
    };
    useAuth.mockReturnValue(authed);
    const {rerender} = renderHook(() => useMainMenuState(), {wrapper});
    expect(refreshProfile).toHaveBeenCalledTimes(1);

    useAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      logout: vi.fn(),
      refreshProfile,
    });
    rerender();
    expect(refreshProfile).toHaveBeenCalledTimes(1);

    useAuth.mockReturnValue(authed);
    rerender();
    expect(refreshProfile).toHaveBeenCalledTimes(2);
  });

  it('plays the nav intro fade when layout transitions from loading to ready', () => {
    vi.useFakeTimers();
    const {result, rerender} = renderHook(() => useMainMenuState(), {wrapper});
    expect(result.current.navIntroFade).toBe(false);

    layoutValue = {state: 'ready', menus: [makeMenu('main', [item])], footer: null, error: null};
    rerender();

    act(() => vi.advanceTimersByTime(0));
    expect(result.current.navIntroFade).toBe(true);
  });

  it('does not play the intro fade when there are no menu items', () => {
    vi.useFakeTimers();
    const {result, rerender} = renderHook(() => useMainMenuState(), {wrapper});

    layoutValue = {state: 'ready', menus: [makeMenu('main')], footer: null, error: null};
    rerender();
    act(() => vi.advanceTimersByTime(0));
    expect(result.current.navIntroFade).toBe(false);
  });
});
