import {cleanup, render} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/menu/MainMenu';
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
});
