import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/MainMenu';

const useMainMenuState = vi.hoisted(() => vi.fn());

interface MemberMenuProps {
  user: unknown;
  isAuthenticated: boolean;
  isOpen: boolean;
  onAccountClick: () => void;
  onLoginClick: () => void;
  onLogoutClick: () => void;
  onToggle: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

interface MenuTreeProps {
  items: unknown[];
  openItemIndex: number | null;
  onDesktopToggle: (index: number, hasChildren: boolean) => void;
  onDesktopOpen: (index: number, hasChildren: boolean) => void;
  onDesktopClose: () => void;
}

interface MobileMenuPanelProps {
  isMobileOpen: boolean;
  state: unknown;
  user: unknown;
  onClose: () => void;
  onAccountClick: () => void;
  onLoginClick: () => void;
  onLogoutClick: () => void;
}

const childProps = vi.hoisted(() => ({
  memberMenu: {} as MemberMenuProps,
  menuTree: {} as MenuTreeProps,
  mobilePanel: {} as MobileMenuPanelProps,
}));

vi.mock('@/features/layout/components/MainMenu/useMainMenuState', () => ({
  useMainMenuState,
}));

vi.mock('@/features/layout/components/MainMenu/parts/MemberMenu', () => ({
  MemberMenu: (props: unknown) => {
    childProps.memberMenu = props as MemberMenuProps;
    return null;
  },
}));

vi.mock('@/features/layout/components/MainMenu/parts/MenuTree', () => ({
  MenuTree: (props: unknown) => {
    childProps.menuTree = props as MenuTreeProps;
    return null;
  },
}));

vi.mock('@/features/layout/components/MainMenu/parts/MobileMenuPanel', () => ({
  MobileMenuPanel: (props: unknown) => {
    childProps.mobilePanel = props as MobileMenuPanelProps;
    return null;
  },
}));

vi.mock('@/components/ResponsiveBrandImage', () => ({
  ResponsiveBrandImage: () => null,
}));

const menuItem = {
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

const makeState = (overrides: Record<string, unknown> = {}) => ({
  currentDate: 'SUNDAY 24 AUGUST 2026',
  isAuthenticated: false,
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

const fireAnimationEnd = (element: Element, animationName?: string) => {
  // jsdom has no AnimationEvent constructor, so React falls back to the
  // vendor-prefixed webkitAnimationEnd listener. Dispatch that type directly.
  const event = new Event('webkitAnimationEnd', {bubbles: true, cancelable: false});
  if (animationName !== undefined) {
    Object.defineProperty(event, 'animationName', {value: animationName});
  }
  fireEvent(element, event);
};

describe('MainMenu', () => {
  beforeEach(() => {
    useMainMenuState.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders the header landmark, current date, and brand anchors', () => {
    useMainMenuState.mockReturnValue(makeState());
    render(<MainMenu navigate={vi.fn()} />);

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByText('SUNDAY 24 AUGUST 2026')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'UC Merced'})).toBeInTheDocument();
    expect(
      screen.getByRole('link', {name: 'Innovate To Grow'}),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Home'})).toBeInTheDocument();
  });

  it('renders the skeleton when the layout is loading', () => {
    useMainMenuState.mockReturnValue(makeState({state: 'loading'}));
    render(<MainMenu navigate={vi.fn()} />);

    const nav = screen.getByRole('navigation', {name: 'Main menu'});
    expect(nav).toHaveAttribute('aria-busy', 'true');
    expect(document.querySelectorAll('.menu-bar-item--skeleton')).toHaveLength(7);
  });

  it('renders an error message when the layout fails', () => {
    useMainMenuState.mockReturnValue(makeState({state: 'error'}));
    render(<MainMenu navigate={vi.fn()} />);

    expect(screen.getByText('Menu unavailable')).toBeInTheDocument();
  });

  it('renders the menu tree when ready with items', () => {
    const state = makeState({state: 'ready', menuItems: [menuItem], openItemIndex: 1});
    useMainMenuState.mockReturnValue(state);
    render(<MainMenu navigate={vi.fn()} />);

    expect(childProps.menuTree).toBeTruthy();
    expect(childProps.menuTree.items).toEqual([menuItem]);
    expect(childProps.menuTree.openItemIndex).toBe(1);
  });

  it('renders a placeholder when ready but with no menu items', () => {
    useMainMenuState.mockReturnValue(makeState({state: 'ready', menuItems: []}));
    render(<MainMenu navigate={vi.fn()} />);

    expect(screen.getByText('No menu items')).toBeInTheDocument();
  });

  it('applies the intro fade class and clears it on animation end', () => {
    const setNavIntroFade = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({navIntroFade: true, setNavIntroFade}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    const nav = screen.getByRole('navigation', {name: 'Main menu'});
    expect(nav).toHaveClass('menu-nav-intro-fade');

    fireAnimationEnd(nav, 'menuNavIntroFade');
    expect(setNavIntroFade).toHaveBeenCalledWith(false);
  });

  it('ignores non-matching animation end events', () => {
    const setNavIntroFade = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({navIntroFade: true, setNavIntroFade}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    fireAnimationEnd(
      screen.getByRole('navigation', {name: 'Main menu'}),
      'other',
    );
    expect(setNavIntroFade).not.toHaveBeenCalled();
  });

  it('ignores animation end that bubbles from a child element', () => {
    const setNavIntroFade = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', navIntroFade: true, setNavIntroFade}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    const nav = screen.getByRole('navigation', {name: 'Main menu'});
    const child = nav.querySelector('ul') as HTMLElement;
    fireAnimationEnd(child, 'menuNavIntroFade');
    expect(setNavIntroFade).not.toHaveBeenCalled();
  });

  it('toggles the mobile menu when the toggle button is clicked', () => {
    const setIsMobileOpen = vi.fn();
    useMainMenuState.mockReturnValue(makeState({setIsMobileOpen}));
    render(<MainMenu navigate={vi.fn()} />);

    const toggle = screen.getByRole('button', {name: 'Toggle menu'});
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(toggle);
    const updater = setIsMobileOpen.mock.calls[0][0] as (prev: boolean) => boolean;
    expect(updater(false)).toBe(true);
    expect(updater(true)).toBe(false);
  });

  it('marks the toggle button active and expanded when the mobile menu is open', () => {
    useMainMenuState.mockReturnValue(makeState({isMobileOpen: true}));
    render(<MainMenu navigate={vi.fn()} />);

    const toggle = screen.getByRole('button', {name: 'Toggle menu'});
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveClass('is-active');
  });

  it('wires member menu handlers to navigation and logout', () => {
    const setIsMemberDropdownOpen = vi.fn();
    const logout = vi.fn();
    const navigate = vi.fn();
    const state = makeState({
      isAuthenticated: true,
      setIsMemberDropdownOpen,
      logout,
    });
    useMainMenuState.mockReturnValue(state);
    render(<MainMenu navigate={navigate} />);

    const member = childProps.memberMenu;
    expect(member.user).toBe(state.user);
    expect(member.isAuthenticated).toBe(true);
    expect(member.isOpen).toBe(false);

    member.onAccountClick();
    expect(setIsMemberDropdownOpen).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith('/account');

    member.onLoginClick();
    expect(navigate).toHaveBeenCalledWith('/login');

    member.onLogoutClick();
    expect(setIsMemberDropdownOpen).toHaveBeenCalledWith(false);
    expect(logout).toHaveBeenCalled();

    member.onToggle();
    expect(setIsMemberDropdownOpen).toHaveBeenCalled();
    const toggleUpdater = setIsMemberDropdownOpen.mock.calls.at(-1)![0] as (
      prev: boolean,
    ) => boolean;
    expect(toggleUpdater(false)).toBe(true);
    expect(toggleUpdater(true)).toBe(false);
  });

  it('opens the member dropdown on mouse enter only when authenticated', () => {
    const setIsMemberDropdownOpen = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({isAuthenticated: true, setIsMemberDropdownOpen}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    childProps.memberMenu.onMouseEnter();
    expect(setIsMemberDropdownOpen).toHaveBeenCalledWith(true);
    childProps.memberMenu.onMouseLeave();
    expect(setIsMemberDropdownOpen).toHaveBeenCalledWith(false);
  });

  it('does not open the member dropdown on mouse enter when anonymous', () => {
    const setIsMemberDropdownOpen = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({isAuthenticated: false, setIsMemberDropdownOpen}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    childProps.memberMenu.onMouseEnter();
    expect(setIsMemberDropdownOpen).not.toHaveBeenCalled();
  });

  it('wires the mobile panel close and navigation handlers', () => {
    const setIsMobileOpen = vi.fn();
    const logout = vi.fn();
    const navigate = vi.fn();
    const state = makeState({isMobileOpen: true, setIsMobileOpen, logout});
    useMainMenuState.mockReturnValue(state);
    render(<MainMenu navigate={navigate} />);

    const panel = childProps.mobilePanel;
    expect(panel.isMobileOpen).toBe(true);
    expect(panel.state).toBe('ready');
    expect(panel.user).toBeNull();

    panel.onClose();
    expect(setIsMobileOpen).toHaveBeenCalledWith(false);

    panel.onAccountClick();
    expect(setIsMobileOpen).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith('/account');

    panel.onLoginClick();
    expect(setIsMobileOpen).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith('/login');

    panel.onLogoutClick();
    expect(setIsMobileOpen).toHaveBeenCalledWith(false);
    expect(logout).toHaveBeenCalled();
  });

  it('toggles desktop submenu items above the breakpoint', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1200);

    childProps.menuTree.onDesktopToggle(0, true);
    const updater = setOpenItemIndex.mock.calls[0][0] as (
      prev: number | null,
    ) => number | null;
    expect(updater(null)).toBe(0);
    expect(updater(0)).toBeNull();
  });

  it('does not toggle when the item has no children', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1200);

    childProps.menuTree.onDesktopToggle(0, false);
    expect(setOpenItemIndex).not.toHaveBeenCalled();
  });

  it('does not toggle at or below the breakpoint', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(992);

    childProps.menuTree.onDesktopToggle(0, true);
    expect(setOpenItemIndex).not.toHaveBeenCalled();
  });

  it('opens a desktop submenu on hover above the breakpoint', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1200);

    childProps.menuTree.onDesktopOpen(0, true);
    expect(setOpenItemIndex).toHaveBeenCalledWith(0);
  });

  it('does not open on hover without children or below the breakpoint', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1200);
    childProps.menuTree.onDesktopOpen(0, false);
    expect(setOpenItemIndex).not.toHaveBeenCalled();

    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(800);
    childProps.menuTree.onDesktopOpen(0, true);
    expect(setOpenItemIndex).not.toHaveBeenCalled();
  });

  it('closes the desktop submenu on mouse leave above the breakpoint', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1200);

    childProps.menuTree.onDesktopClose();
    expect(setOpenItemIndex).toHaveBeenCalledWith(null);
  });

  it('does not close on mouse leave at or below the breakpoint', () => {
    const setOpenItemIndex = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({state: 'ready', menuItems: [menuItem], setOpenItemIndex}),
    );
    render(<MainMenu navigate={vi.fn()} />);
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(800);

    childProps.menuTree.onDesktopClose();
    expect(setOpenItemIndex).not.toHaveBeenCalled();
  });

  it('uses window.location.assign by default when no navigate prop is given', () => {
    const assign = vi.fn();
    vi.stubGlobal('location', {assign});
    useMainMenuState.mockReturnValue(makeState());
    render(<MainMenu />);

    childProps.memberMenu.onLoginClick();
    expect(assign).toHaveBeenCalledWith('/login');
  });
});
