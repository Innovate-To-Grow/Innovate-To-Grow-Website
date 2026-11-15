import {cleanup, render} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/MainMenu';
import {makeState} from '@/__tests__/features/layout/components/MainMenu/menu/mainMenuFixtures';

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
});
