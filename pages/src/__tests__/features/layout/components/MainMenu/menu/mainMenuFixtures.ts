// Fixtures shared by the MainMenu*.test.tsx files: a menu item with one child, and the
// useMainMenuState result each file's mock returns.
import {vi} from 'vitest';

export const menuItem = {
  title: 'Parent',
  url: '/parent',
  type: 'app',
  open_in_new_tab: false,
  children: [
    {
      title: 'Child',
      url: '/child',
      type: 'app',
      open_in_new_tab: false,
      children: [],
    },
  ],
};

export const makeState = (overrides: Record<string, unknown> = {}) => ({
  isAuthenticated: false,
  hasMemberIdentity: false,
  isMemberDropdownOpen: false,
  isMobileOpen: false,
  logout: vi.fn(),
  menuItems: [] as unknown[],
  navIntroFade: false,
  openItemIndex: null as number | null,
  setIsMemberDropdownOpen: vi.fn(),
  setIsMobileOpen: vi.fn(),
  setNavIntroFade: vi.fn(),
  setOpenItemIndex: vi.fn(),
  state: 'ready',
  user: null,
  ...overrides,
});
