import {cleanup, fireEvent, render, screen} from '@testing-library/react';
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

  it('renders an error message when the layout fails', () => {
    useMainMenuState.mockReturnValue(makeState({state: 'error'}));
    render(<MainMenu navigate={vi.fn()} />);

    expect(screen.getByText('Menu unavailable')).toBeInTheDocument();
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
});
