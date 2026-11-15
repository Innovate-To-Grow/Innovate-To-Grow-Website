import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/menu/MainMenu';
import {ROUTE_CHANGE_EVENT} from '@/features/layout/hooks/useCurrentPathname';
import {makeState, menuItem} from '@/__tests__/features/layout/components/MainMenu/menu/mainMenuFixtures';

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

vi.mock('@/features/layout/components/MainMenu/menu/useMainMenuState', () => ({
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

vi.mock('@/components/ResponsiveBrandImage/ResponsiveBrandImage', () => ({
  ResponsiveBrandImage: () => null,
}));

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
