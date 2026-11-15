import {cleanup, render, screen, within} from '@testing-library/react';
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
});
