import {fireEvent, screen} from '@testing-library/react';
import type {User} from '@/features/auth/api/contracts/types';
import type {MenuItem} from '@/features/layout/api';
import type {LayoutLoadState} from '@/features/layout/components/LayoutProvider/context';

export const projects: MenuItem = {
  title: 'Projects',
  url: '/projects',
  type: 'app',
  open_in_new_tab: false,
  children: [
    {title: 'Current Projects', url: '/current-projects', type: 'app', open_in_new_tab: false, children: []},
    {title: 'Past Projects', url: '/past-projects', type: 'app', open_in_new_tab: false, children: []},
  ],
};

export const news: MenuItem = {title: 'News', url: '/news', type: 'app', open_in_new_tab: false, children: []};

export interface HarnessProps {
  menuItems?: MenuItem[];
  state?: LayoutLoadState;
  hasMemberIdentity?: boolean;
  user?: User | null;
  current?: {menuIndex: number | null; currentPath: string; isExact: boolean} | null;
  initiallyOpen?: boolean;
  withTrigger?: boolean;
  handlers?: {onAccountClick?: () => void; onLoginClick?: () => void; onLogoutClick?: () => void};
}

export const getPanel = () => document.getElementById('mobile-menu') as HTMLElement;
export const getTrigger = () => screen.getByRole('button', {name: 'Toggle menu'});

/** Presses Tab (or Shift+Tab); true when the keypress was left to the browser's own focus move. */
export const pressTab = (shiftKey = false) => fireEvent.keyDown(document, {key: 'Tab', shiftKey});
