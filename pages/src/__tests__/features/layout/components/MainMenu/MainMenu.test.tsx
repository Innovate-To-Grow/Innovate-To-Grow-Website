import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/MainMenu';
import {ROUTE_CHANGE_EVENT} from '@/features/layout/hooks/useCurrentPathname';

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

  it('renders the blue bar, the site-name band and the menu row with the date, without a badge', () => {
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

    const siteName = screen.getByRole('link', {name: 'Innovate To Grow School of Engineering'});
    expect(siteName).toHaveAttribute('href', '/');
    expect(siteName.querySelector('.site-header-sitename-title')).toHaveTextContent(/^Innovate To Grow$/);
    expect(siteName.querySelector('.site-header-sitename-subtitle')).toHaveTextContent(/^School of Engineering$/);

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
      section: null,
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

  describe('scroll behaviour', () => {
    const setScrollY = (value: number) => {
      Object.defineProperty(window, 'scrollY', {configurable: true, value});
    };

    afterEach(() => {
      setScrollY(0);
    });

    it('tucks the site-name band away after scrolling down and never leaves its room empty', () => {
      vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
        callback(0);
        return 1;
      });
      // The phone band is 84px tall: #menu-root keeps that room for it under the fixed bar.
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
        const height = this.classList.contains('site-header-band') ? 84 : 0;
        return {height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})} as DOMRect;
      });
      useMainMenuState.mockReturnValue(makeState());
      render(<MainMenu navigate={vi.fn()} />);
      const header = screen.getByRole('banner');
      const scrollTo = (value: number) =>
        act(() => {
          setScrollY(value);
          window.dispatchEvent(new Event('scroll'));
        });
      expect(header).not.toHaveClass('is-band-hidden');

      // Still over its own room: hiding it here would uncover an empty strip.
      scrollTo(60);
      expect(header).not.toHaveClass('is-band-hidden');

      scrollTo(120);
      expect(header).toHaveClass('is-band-hidden');

      // Scrolling back up: it returns as soon as its room comes into view, not only at the top.
      scrollTo(20);
      expect(header).not.toHaveClass('is-band-hidden');

      scrollTo(120);
      expect(header).toHaveClass('is-band-hidden');
      scrollTo(0);
      expect(header).not.toHaveClass('is-band-hidden');
    });

    it('publishes the header part heights as CSS custom properties', () => {
      useMainMenuState.mockReturnValue(makeState());
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
        const height = this.classList.contains('site-header-bar')
          ? 85
          : this.classList.contains('site-header-band')
            ? 109.6
            : this.classList.contains('site-header-menu')
              ? 44
              : 0;
        return {height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})} as DOMRect;
      });
      render(<MainMenu navigate={vi.fn()} />);

      const style = document.documentElement.style;
      expect(style.getPropertyValue('--itg-header-bar-height')).toBe('85px');
      expect(style.getPropertyValue('--itg-header-band-height')).toBe('109.6px');
      expect(style.getPropertyValue('--itg-header-menu-height')).toBe('44px');
    });

    it('marks the header while the mobile menu is open', () => {
      useMainMenuState.mockReturnValue(makeState({isMobileOpen: true}));
      render(<MainMenu navigate={vi.fn()} />);
      expect(screen.getByRole('banner')).toHaveClass('is-mobile-open');
    });
  });
});
