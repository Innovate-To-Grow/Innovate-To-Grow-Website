import {act, renderHook, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {useMainMenuState} from '@/features/layout/components/MainMenu/useMainMenuState';
import type {Menu} from '@/features/layout/api';

const mainMenuStateMocks = vi.hoisted(() => ({
  authValue: {
    user: null,
    isAuthenticated: false,
    logout: vi.fn(),
    refreshProfile: vi.fn(),
  },
  menuValue: {
    menu: null as Menu | null,
    state: 'loading' as const,
    error: null,
  },
}));

vi.mock('@/features/layout/components/LayoutProvider/context', () => ({
  useMenu: () => mainMenuStateMocks.menuValue,
}));

vi.mock('@/features/auth', () => ({
  useAuth: () => mainMenuStateMocks.authValue,
}));

const menu: Menu = {
  id: 'menu-1',
  name: 'main-nav',
  display_name: 'Main',
  description: null,
  created_at: '',
  updated_at: '',
  items: [
    {
      type: 'app',
      title: 'Projects',
      url: '/projects',
      open_in_new_tab: false,
      children: [],
    },
  ],
};

describe('useMainMenuState', () => {
  beforeEach(() => {
    vi.useRealTimers();
    document.body.style.overflow = '';
    vi.clearAllMocks();
    mainMenuStateMocks.menuValue = {
      menu,
      state: 'ready',
      error: null,
    };
    mainMenuStateMocks.authValue = {
      user: null,
      isAuthenticated: false,
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    };
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 500,
    });
  });

  it('toggles the mobile menu from the global toggle event and locks body scroll', () => {
    const {result, unmount} = renderHook(() => useMainMenuState());

    act(() => {
      window.dispatchEvent(new Event('toggle-menu'));
    });
    expect(result.current.isMobileOpen).toBe(true);
    expect(document.body.style.overflow).toBe('hidden');

    act(() => {
      window.innerWidth = 1200;
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current.isMobileOpen).toBe(false);

    unmount();
    expect(document.body.style.overflow).toBe('');
  });

  it('refreshes the member profile once when an authenticated user lacks an avatar', async () => {
    mainMenuStateMocks.authValue = {
      user: {id: 1, email: 'member@example.com', profile_image: ''},
      isAuthenticated: true,
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    };

    renderHook(() => useMainMenuState());

    await waitFor(() => expect(mainMenuStateMocks.authValue.refreshProfile).toHaveBeenCalledTimes(1));
  });

  it('plays the nav intro fade when layout moves from loading to ready with menu items', () => {
    vi.useFakeTimers();
    mainMenuStateMocks.menuValue = {
      menu: null,
      state: 'loading',
      error: null,
    };
    const {result, rerender} = renderHook(() => useMainMenuState());

    mainMenuStateMocks.menuValue = {
      menu,
      state: 'ready',
      error: null,
    };

    rerender();
    act(() => {
      vi.runOnlyPendingTimers();
    });

    expect(result.current.navIntroFade).toBe(true);
    vi.useRealTimers();
  });
});
