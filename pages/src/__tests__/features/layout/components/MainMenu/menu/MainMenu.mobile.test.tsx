import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/menu/MainMenu';
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
});
