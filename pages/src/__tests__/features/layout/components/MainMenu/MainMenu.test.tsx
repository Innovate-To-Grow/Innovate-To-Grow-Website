import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/MainMenu';
import {ROUTE_CHANGE_EVENT} from '@/features/layout/hooks/useCurrentPathname';
import {makeState, menuItem} from '@/__tests__/features/layout/components/MainMenu/mainMenuFixtures';

const useMainMenuState = vi.hoisted(() => vi.fn());

interface MemberMenuProps {
  user: unknown;
  hasMemberIdentity: boolean;
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
  current: {menuIndex: number | null; currentPath: string; isExact: boolean} | null;
  onDesktopToggle: (index: number, hasChildren: boolean) => void;
  onDesktopOpen: (index: number, hasChildren: boolean) => void;
  onDesktopClose: () => void;
}

interface MobileMenuPanelProps {
  isMobileOpen: boolean;
  current: {menuIndex: number | null; currentPath: string; isExact: boolean} | null;
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
    vi.useRealTimers();
  });

  it('renders the blue bar and then the menu row with the date, without a site-name band or a badge', () => {
    vi.useFakeTimers({toFake: ['Date']});
    vi.setSystemTime(new Date(2026, 8, 20, 10, 30));
    useMainMenuState.mockReturnValue(makeState());
    const {container} = render(<MainMenu navigate={vi.fn()} />);

    expect(screen.getByRole('banner')).toBeInTheDocument();
    const bar = container.querySelector('.site-header-bar') as HTMLElement;
    const ucm = within(bar).getByRole('link', {name: 'UC Merced'});
    expect(ucm).toHaveAttribute('href', 'https://www.ucmerced.edu');
    expect(within(bar).getByRole('link', {name: 'Innovate To Grow home'})).toHaveAttribute('href', '/');

    const university = within(bar).getByRole('navigation', {name: 'UC Merced'});
    expect(within(university).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Directory',
      'Apply',
      'Give',
    ]);

    // No site-name band: the menu row follows the blue bar directly.
    expect(bar.nextElementSibling).toBe(container.querySelector('.site-header-menu'));
    expect(screen.queryByText('School of Engineering')).toBeNull();

    expect(container.querySelector('.site-header-menu')).toContainElement(
      screen.getByRole('navigation', {name: 'Main menu'}),
    );
    // The current date sits at the right end of the menu row, next to the member link.
    const utility = container.querySelector('.site-header-menu .site-header-utility') as HTMLElement;
    const date = utility.querySelector('time.site-header-date');
    expect(date).toHaveTextContent(/^Sunday 20 September 2026$/);
    expect(date).toHaveAttribute('dateTime', '2026-09-20');
    expect(container.querySelector('.site-header-badge')).toBeNull();
    expect(screen.queryByRole('link', {name: 'Home'})).toBeNull();
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
    expect(childProps.menuTree.current).toEqual({
      menuIndex: null,
      currentPath: '/',
      isExact: true,
    });
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
      hasMemberIdentity: true,
      setIsMemberDropdownOpen,
      logout,
    });
    useMainMenuState.mockReturnValue(state);
    render(<MainMenu navigate={navigate} />);

    const member = childProps.memberMenu;
    expect(member.user).toBe(state.user);
    expect(member.hasMemberIdentity).toBe(true);
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
      makeState({isAuthenticated: true, hasMemberIdentity: true, setIsMemberDropdownOpen}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    childProps.memberMenu.onMouseEnter();
    expect(setIsMemberDropdownOpen).toHaveBeenCalledWith(true);
    childProps.memberMenu.onMouseLeave();
    expect(setIsMemberDropdownOpen).toHaveBeenCalledWith(false);
  });

  it('keeps the member dropdown open on the click that follows a hover', () => {
    const setIsMemberDropdownOpen = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({isAuthenticated: true, hasMemberIdentity: true, setIsMemberDropdownOpen}),
    );
    render(<MainMenu navigate={vi.fn()} />);

    childProps.memberMenu.onMouseEnter();
    childProps.memberMenu.onToggle();
    const afterHover = setIsMemberDropdownOpen.mock.calls.at(-1)![0] as (prev: boolean) => boolean;
    expect(afterHover(true)).toBe(true);

    // A second click toggles as usual.
    childProps.memberMenu.onToggle();
    const secondClick = setIsMemberDropdownOpen.mock.calls.at(-1)![0] as (prev: boolean) => boolean;
    expect(secondClick(true)).toBe(false);
  });

  it('does not reopen the member dropdown on mouse enter while it is open', () => {
    const setIsMemberDropdownOpen = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({
        isAuthenticated: true,
        hasMemberIdentity: true,
        isMemberDropdownOpen: true,
        setIsMemberDropdownOpen,
      }),
    );
    render(<MainMenu navigate={vi.fn()} />);

    // Opened by a click: the pointer arriving afterwards must not turn the next click into a no-op.
    childProps.memberMenu.onMouseEnter();
    expect(setIsMemberDropdownOpen).not.toHaveBeenCalled();
    childProps.memberMenu.onToggle();
    const toggle = setIsMemberDropdownOpen.mock.calls.at(-1)![0] as (prev: boolean) => boolean;
    expect(toggle(true)).toBe(false);
  });

  it('does not open the member dropdown on mouse enter when anonymous', () => {
    const setIsMemberDropdownOpen = vi.fn();
    useMainMenuState.mockReturnValue(
      makeState({isAuthenticated: false, hasMemberIdentity: false, setIsMemberDropdownOpen}),
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

  it('offers a skip link that moves focus to the main landmark', () => {
    // index.html's page container: a native <main id="main">.
    const main = document.createElement('main');
    main.id = 'main';
    document.body.appendChild(main);
    try {
      useMainMenuState.mockReturnValue(makeState());
      render(<MainMenu navigate={vi.fn()} />);

      const skip = screen.getByRole('link', {name: 'Skip to main content'});
      expect(screen.getByRole('banner').firstElementChild).toBe(skip);
      fireEvent.click(skip);
      expect(screen.getByRole('main')).toBe(main);
      expect(main).toHaveFocus();
      expect(main).toHaveAttribute('tabindex', '-1');
      expect(window.location.hash).toBe('');
    } finally {
      main.remove();
    }
  });

  it('keeps a tabindex the main landmark already has, and leaves the link alone without one', () => {
    useMainMenuState.mockReturnValue(makeState());
    render(<MainMenu navigate={vi.fn()} />);
    const skip = screen.getByRole('link', {name: 'Skip to main content'});
    try {
      // No main landmark on the page: the click keeps its default.
      expect(fireEvent.click(skip)).toBe(true);

      const main = document.createElement('div');
      main.id = 'main';
      main.tabIndex = 0;
      document.body.appendChild(main);
      try {
        expect(fireEvent.click(skip)).toBe(false);
        expect(main).toHaveFocus();
        expect(main).toHaveAttribute('tabindex', '0');
      } finally {
        main.remove();
      }
    } finally {
      window.history.replaceState(null, '', '/');
    }
  });

  describe('current section', () => {
    afterEach(() => {
      window.history.replaceState(null, '', '/');
    });

    it('resolves the current section from the location and passes it to both menus', () => {
      window.history.replaceState(null, '', '/child');
      useMainMenuState.mockReturnValue(makeState({state: 'ready', menuItems: [menuItem]}));
      render(<MainMenu navigate={vi.fn()} />);

      expect(childProps.menuTree.current).toMatchObject({menuIndex: 0, currentPath: '/child', isExact: true});
      expect(childProps.mobilePanel.current).toMatchObject({menuIndex: 0, currentPath: '/child'});
    });

    it('follows in-app route changes announced by the page shell and back/forward', () => {
      useMainMenuState.mockReturnValue(makeState({state: 'ready', menuItems: [menuItem]}));
      render(<MainMenu navigate={vi.fn()} />);
      expect(childProps.menuTree.current?.menuIndex).toBeNull();

      act(() => {
        window.history.pushState(null, '', '/child');
        window.dispatchEvent(new CustomEvent(ROUTE_CHANGE_EVENT, {detail: {pathname: '/child'}}));
      });
      expect(childProps.menuTree.current?.menuIndex).toBe(0);

      act(() => {
        window.history.replaceState(null, '', '/elsewhere');
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      expect(childProps.menuTree.current?.menuIndex).toBeNull();
    });
  });
});
