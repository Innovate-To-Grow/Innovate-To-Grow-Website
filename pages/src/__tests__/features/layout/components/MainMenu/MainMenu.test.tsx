import {fireEvent, render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/MainMenu';
import type {MenuItem} from '@/features/layout/api';

const mainMenuMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  state: {
    currentDate: 'Monday, June 8, 2026',
    isAuthenticated: false,
    isMemberDropdownOpen: false,
    isMobileOpen: false,
    logout: vi.fn(),
    menuItems: [] as MenuItem[],
    navIntroFade: false,
    openItemIndex: null as number | null,
    setIsMemberDropdownOpen: vi.fn(),
    setIsMobileOpen: vi.fn(),
    setNavIntroFade: vi.fn(),
    setOpenItemIndex: vi.fn(),
    state: 'loading' as const,
    user: null,
  },
}));

vi.mock('@/app/router', () => ({
  router: {
    navigate: mainMenuMocks.navigate,
  },
}));

vi.mock('@/features/layout/components/MainMenu/useMainMenuState', () => ({
  useMainMenuState: () => mainMenuMocks.state,
}));

const item: MenuItem = {
  type: 'app',
  title: 'Projects',
  url: '/projects',
  open_in_new_tab: false,
  children: [],
};

const parentItem: MenuItem = {
  type: 'app',
  title: 'Explore',
  url: '/explore',
  open_in_new_tab: false,
  children: [
    {
      type: 'app',
      title: 'Child Page',
      url: '/child',
      open_in_new_tab: false,
      children: [],
    },
  ],
};

describe('MainMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mainMenuMocks.state = {
      currentDate: 'Monday, June 8, 2026',
      isAuthenticated: false,
      isMemberDropdownOpen: false,
      isMobileOpen: false,
      logout: vi.fn(),
      menuItems: [],
      navIntroFade: false,
      openItemIndex: null,
      setIsMemberDropdownOpen: vi.fn(),
      setIsMobileOpen: vi.fn(),
      setNavIntroFade: vi.fn(),
      setOpenItemIndex: vi.fn(),
      state: 'loading',
      user: null,
    };
  });

  it('renders loading and error navigation states', () => {
    const {container, rerender} = render(<MainMenu />);

    expect(container.querySelector('.menu-bar-list--skeleton')).not.toBeNull();

    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      state: 'error',
    };
    rerender(<MainMenu />);

    expect(screen.getByText('Menu unavailable')).toBeInTheDocument();
  });

  it('renders ready menu states and handles member navigation actions', () => {
    const {rerender} = render(<MainMenu />);

    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      state: 'ready',
      menuItems: [],
    };
    rerender(<MainMenu />);
    expect(screen.getByText('No menu items')).toBeInTheDocument();

    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      state: 'ready',
      menuItems: [item],
    };
    rerender(<MainMenu />);
    expect(screen.getAllByRole('link', {name: 'Projects'})).toHaveLength(2);

    fireEvent.click(screen.getAllByRole('button', {name: /sign in/i})[0]);
    expect(mainMenuMocks.navigate).toHaveBeenCalledWith('/login');
  });

  it('routes account and logout clicks for authenticated users', () => {
    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      state: 'ready',
      isAuthenticated: true,
      isMemberDropdownOpen: true,
      user: {id: 1, email: 'member@example.com', profile_image: ''},
      logout: vi.fn(),
    };

    render(<MainMenu />);

    fireEvent.click(screen.getAllByRole('button', {name: /account/i})[0]);
    expect(mainMenuMocks.state.setIsMemberDropdownOpen).toHaveBeenCalledWith(false);
    expect(mainMenuMocks.navigate).toHaveBeenCalledWith('/account');

    fireEvent.click(screen.getAllByRole('button', {name: /sign out/i})[0]);
    expect(mainMenuMocks.state.logout).toHaveBeenCalledTimes(1);
  });

  it('handles desktop menu expansion and nav intro animation completion', () => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 1200,
    });
    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      state: 'ready',
      navIntroFade: true,
      menuItems: [parentItem],
    };

    const {container} = render(<MainMenu />);
    const parentLink = screen.getAllByRole('link', {name: 'Explore'})[0];
    const parentItemElement = parentLink.closest('li')!;

    fireEvent.mouseEnter(parentItemElement);
    expect(mainMenuMocks.state.setOpenItemIndex).toHaveBeenCalledWith(0);

    parentLink.addEventListener('click', (event) => event.preventDefault());
    fireEvent.click(parentLink);
    const toggleUpdater = mainMenuMocks.state.setOpenItemIndex.mock.calls.at(-1)?.[0] as (value: number | null) => number | null;
    expect(toggleUpdater(null)).toBe(0);
    expect(toggleUpdater(0)).toBeNull();

    fireEvent.mouseLeave(parentItemElement);
    expect(mainMenuMocks.state.setOpenItemIndex).toHaveBeenCalledWith(null);

    expect(container.querySelector('.menu-nav-intro-fade')).not.toBeNull();
  });

  it('routes mobile menu auth actions and close controls', () => {
    const setMobileOpen = vi.fn();
    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      state: 'ready',
      isMobileOpen: true,
      setIsMobileOpen: setMobileOpen,
      menuItems: [item],
    };

    const {rerender} = render(<MainMenu />);

    fireEvent.click(screen.getByRole('button', {name: 'Toggle menu'}));
    const toggleUpdater = setMobileOpen.mock.calls.at(-1)?.[0] as (value: boolean) => boolean;
    expect(toggleUpdater(false)).toBe(true);
    expect(toggleUpdater(true)).toBe(false);

    fireEvent.click(screen.getByRole('button', {name: 'Close menu'}));
    expect(setMobileOpen).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('button', {name: /Sign In \/ Sign Up/}));
    expect(setMobileOpen).toHaveBeenCalledWith(false);
    expect(mainMenuMocks.navigate).toHaveBeenCalledWith('/login');

    const logout = vi.fn();
    mainMenuMocks.state = {
      ...mainMenuMocks.state,
      isAuthenticated: true,
      isMemberDropdownOpen: false,
      user: {member_uuid: 'member-1', email: 'member@example.com'},
      logout,
    };
    rerender(<MainMenu />);

    fireEvent.click(screen.getAllByRole('button', {name: 'Account'}).at(-1)!);
    expect(setMobileOpen).toHaveBeenCalledWith(false);
    expect(mainMenuMocks.navigate).toHaveBeenCalledWith('/account');

    fireEvent.click(screen.getAllByRole('button', {name: 'Sign Out'}).at(-1)!);
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
